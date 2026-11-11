"""Read-only native iD navigation state, with optional private area checks.

This module takes no action and does not establish imagery coverage, geographic
edits or saving. It reads only the iframe's parsed ``map`` hash parameter;
OAuth-bearing DOM attributes and the complete iframe URL/hash are never saved.
No production task or probe enables this optional reader automatically.
"""
import math
from urllib.parse import urlsplit


OUTER_READ = r'''() => {
  const visible = e => !!e && !!e.getClientRects().length &&
    getComputedStyle(e).visibility !== 'hidden' &&
    getComputedStyle(e).display !== 'none';
  const embeds = document.querySelectorAll('#id-embed');
  const embed = embeds.length === 1 ? embeds[0] : null;
  return {outer_url: location.origin + location.pathname,
    embed_count: embeds.length,
    configured: !!embed && embed.getAttribute('data-configured') === 'true',
    embed_visible: visible(embed)};
}'''

FRAME_READ = r'''() => {
  const visible = e => !!e && !!e.getClientRects().length &&
    getComputedStyle(e).visibility !== 'hidden' &&
    getComputedStyle(e).display !== 'none';
  const values = new URLSearchParams(location.hash.slice(1)).getAll('map');
  let nativeMap = null;
  if (values.length === 1 && /^\d+(?:\.\d+)?\/[-+]?\d+(?:\.\d+)?\/[-+]?\d+(?:\.\d+)?$/.test(values[0])) {
    const [zoom, lat, lon] = values[0].split('/').map(Number);
    if ([zoom, lat, lon].every(Number.isFinite) && zoom > 0 && zoom <= 30 &&
        lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      nativeMap = {zoom, lat, lon};
    }
  }
  return {iframe_url: location.origin + location.pathname,
    iframe_path: location.pathname,
    map_visible: [...document.querySelectorAll('#id-container .main-map')].some(visible),
    native_map: nativeMap,
    visible_button_labels: [...document.querySelectorAll('button')].filter(visible)
      .map(e => (e.getAttribute('aria-label') || e.getAttribute('title') || e.innerText || '').trim())
      .filter(Boolean)};
}'''


def read_editor_state(page):
    """Capture current native editor state without waiting or changing its view.

    ``outer_url`` and ``iframe_url`` contain origin/path only. Missing embeds or
    frames return an explicitly incomplete state. Browser transport failures
    propagate to the caller as runtime failures rather than fabricated success.
    """
    outer = page.evaluate(OUTER_READ)
    state = {
        'outer_url': outer['outer_url'],
        'configured': outer['configured'],
        'embed_visible': outer['embed_visible'],
        'iframe_url': None,
        'iframe_path': None,
        'map_visible': False,
        'native_map': None,
        'visible_button_labels': [],
    }
    if outer['embed_count'] != 1:
        return state
    # Immediate lookup: this reader observes state; it must not start a new
    # implicit locator wait while an iframe is being replaced.
    handle = page.query_selector('#id-embed')
    frame = handle.content_frame() if handle is not None else None
    if frame is not None:
        state.update(frame.evaluate(FRAME_READ))
    return state


def _numeric_view(value):
    if not isinstance(value, dict) or set(value) != {'zoom', 'lat', 'lon'}:
        return None
    if any(type(value[k]) not in (int, float) for k in ('zoom', 'lat', 'lon')):
        return None
    if not all(math.isfinite(value[k]) for k in ('zoom', 'lat', 'lon')):
        return None
    if not (0 < value['zoom'] <= 30 and -90 <= value['lat'] <= 90 and
            -180 <= value['lon'] <= 180):
        return None
    return value


def _origin(url, *, configured=False):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username is not None or parsed.password is not None):
        return None
    if configured and (parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        return None
    host = parsed.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if port == (80 if parsed.scheme == 'http' else 443):
        port = None
    return parsed.scheme + '://' + host + (':' + str(port) if port is not None else '')


def _native_precision(zoom):
    # Both pinned OSM.formatHash and native iD.behaviorHash use this precision.
    return max(0, math.ceil(math.log2(zoom)))


def _same_center(expected, actual):
    tolerance = (0.5 * 10 ** -_native_precision(expected['zoom']) +
                 0.5 * 10 ** -_native_precision(actual['zoom']) + 1e-9)
    longitude_difference = abs((actual['lon'] - expected['lon'] + 180) % 360 - 180)
    return (abs(actual['lat'] - expected['lat']) <= tolerance and
            longitude_difference <= tolerance)


def checks(spec, state, site_origin):
    """Terminal navigation checks; no actor hints, coverage or save claims.

    ``spec`` is ``{}`` or contains a private ``expected_center`` with numeric
    ``zoom``, ``lat`` and ``lon`` captured from the native initial map view. Its
    zoom supplies native coordinate precision and does not constrain final
    zoom. Invalid configuration raises; missing/malformed observed state fails.
    """
    if not isinstance(spec, dict) or set(spec) - {'expected_center'}:
        raise ValueError('Unsupported native editor navigation specification')
    origin = _origin(site_origin, configured=True)
    if origin is None:
        raise ValueError('Explicit website origin required')
    expected = None
    if 'expected_center' in spec:
        expected = _numeric_view(spec['expected_center'])
        if expected is None:
            raise ValueError('Native initial center and zoom required')
    if not isinstance(state, dict):
        state = {}
    outer = state.get('outer_url')
    frame = state.get('iframe_url')
    outer_local = _origin(outer) == origin
    frame_local = _origin(frame) == origin
    view = _numeric_view(state.get('native_map'))
    result = {
        'local_editor_page': outer_local and urlsplit(outer).path == '/edit',
        'native_editor_frame': frame_local and urlsplit(frame).path == '/id' and
                               state.get('iframe_path') == '/id',
        'editor_configured': state.get('configured') is True,
        'editor_embed_visible': state.get('embed_visible') is True,
        'editor_map_visible': state.get('map_visible') is True,
        'native_map_state': view is not None,
    }
    if expected is not None:
        result['requested_area'] = view is not None and _same_center(expected, view)
    return result


def navigation_context_changed(error):
    """Recognize only transient document/frame replacement from Playwright.

    A closed page/browser, script exception or arbitrary transport error is not
    a readiness event and must propagate. Callers retain one absolute deadline.
    """
    from playwright.sync_api import Error as BrowserError
    if not isinstance(error, BrowserError):
        return False
    text = str(error).lower()
    if any(marker in text for marker in (
            'target page, context or browser has been closed',
            'browser has been closed', 'connection closed', 'target crashed')):
        return False
    return any(marker in text for marker in (
        'execution context was destroyed', 'cannot find context with specified id',
        'frame was detached'))
