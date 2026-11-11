"""Optional public Map capabilities, never an actor or task-admission adapter.

All checks describe the captured native capability. Query content must match a
separate full-document reference; this does not score an actor answer or prove
understanding. Share output is a link artifact, not proof of sending to anyone.
"""
import hashlib
import math
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from .map_metadata_query import native_geo_uri
from .map_share_query import short_path
from .site_navigation_rules import evaluate_navigation

VERSION = 'map-local-capabilities-v2'
DOCUMENTS = {
    '/copyright': 'Copyright and License',
    '/about': 'OpenStreetMap provides map data for thousands of websites, mobile apps, and hardware devices',
    '/communities': 'Communities',
}
UPLOAD_FORM = {
    'fields': ['trace[gpx_file]', 'trace[description]', 'trace[tagstring]', 'trace[visibility]'],
    'submit_text': 'Upload',
}


def normalize(text):
    if not isinstance(text, str):
        raise ValueError('Explicit native text required')
    return ' '.join(text.split())


def digest(text):
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def origin(url):
    if not isinstance(url, str):
        raise ValueError('Explicit native URL required')
    p = urlsplit(url)
    if (p.scheme not in ('http', 'https') or not p.hostname or
            p.username is not None or p.password is not None):
        raise ValueError('Invalid public URL origin')
    return p.scheme, p.hostname.lower(), p.port or (80 if p.scheme == 'http' else 443)


def local_target(site_origin, href, expected_path):
    """Follow an actually observed ordinary native href, not an invented route."""
    if not isinstance(href, str) or not href or '\\' in href:
        raise ValueError('Missing ordinary native href')
    target = urljoin(site_origin.rstrip('/') + '/', href)
    p = urlsplit(target)
    if origin(target) != origin(site_origin) or p.path != expected_path:
        raise ValueError('Native link does not identify the requested local page')
    if set(parse_qs(p.query, keep_blank_values=True)) - {'query', 'engine', 'route'}:
        raise ValueError('Private or unexpected URL query is not public capability evidence')
    if set(parse_qs(p.fragment, keep_blank_values=True)) - {'map', 'layers'}:
        raise ValueError('Private or unexpected fragment is not public capability evidence')
    return target


def map_triplet(path):
    values = parse_qs(urlsplit(path).fragment, keep_blank_values=True).get('map', [])
    if len(values) != 1 or not re.fullmatch(r'\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?', values[0]):
        raise ValueError('Explicit native public map fragment required')
    z, lat, lon = values[0].split('/')
    out = int(z), float(lat), float(lon)
    native_geo_uri(*out)
    return out


def geo_triplet(view):
    match = re.fullmatch(r'geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)',
                         (view or {}).get('native_geo_uri', ''))
    if not match:
        raise ValueError('Native public center is unavailable')
    lat, lon = map(float, match.groups()[:2])
    z = int(match[3])
    native_geo_uri(z, lat, lon)
    return z, lat, lon


def same_center(expected, actual):
    z, lat, lon = expected
    az, alat, alon = actual
    precision = math.ceil(math.log2(z))
    tolerance = .5 * 10 ** -precision + 1e-8
    return z == az and abs(lat - alat) <= tolerance and abs((lon-alon+180) % 360-180) <= tolerance


def document_content(body, path):
    """Canonical complete public document, excluding its variable site banner.

    The old independent reference capture and the live reader use the same
    visible heading boundary. No paragraph, step or token limit is applied.
    """
    if not isinstance(body, str):
        raise ValueError('Complete native document text missing')
    heading = DOCUMENTS[path]
    lines = [normalize(line) for line in body.splitlines() if normalize(line)]
    matches = [i for i, line in enumerate(lines) if line == heading]
    if len(matches) != 1:
        raise ValueError('Native document heading is missing or ambiguous')
    content = '\n'.join(lines[matches[0]:])
    if len(content.split()) < 30:
        raise ValueError('A document heading alone is not information retrieval')
    return content


def ax_names(ax):
    """Public static-text names in native CDP traversal order."""
    if not isinstance(ax, dict) or not isinstance(ax.get('nodes'), list):
        raise ValueError('Full native accessibility tree required')
    nodes = ax['nodes']
    by_id = {r['nodeId']: r for r in nodes if 'nodeId' in r}
    roots = [r for r in nodes if r.get('role', {}).get('value') == 'RootWebArea']
    ordered, seen = [], set()
    def visit(row):
        key = row.get('nodeId', id(row))
        if key in seen: return
        seen.add(key)
        ordered.append(row)
        for child in row.get('childIds', []):
            if child in by_id: visit(by_id[child])
    if roots:
        for root in roots: visit(root)
    else:
        ordered = nodes
    return [r['name']['value'] for r in ordered
            if not r.get('ignored') and r.get('role', {}).get('value') == 'StaticText'
            and isinstance(r.get('name', {}).get('value'), str)]


def full_text_exposed(content, ax):
    # Inline links/superscripts can split native StaticText at punctuation.
    # Require every content token in document order; no first-N text shortcut.
    wanted = re.findall(r'\w+', content, flags=re.UNICODE)
    available = iter(re.findall(r'\w+', ' '.join(ax_names(ax)), flags=re.UNICODE))
    return bool(wanted) and all(any(token == next_token for next_token in available) for token in wanted)


def document_checks(path, page, reference, site_origin):
    required = {'content', 'content_sha256', 'reference_evidence'}
    if not isinstance(reference, dict) or not required <= set(reference):
        raise ValueError('Independent complete document reference required')
    if digest(reference['content']) != reference['content_sha256']:
        raise ValueError('Independent content reference changed')
    proofs = reference['reference_evidence']
    if len(proofs) != 2 or len({r['file'] for r in proofs}) != 2:
        raise ValueError('Two distinct full native document references required')
    contract = {'domain': 'map', 'completion': {'path_regex': re.escape(path) + '/?',
                                               'heading_regex': '^' + re.escape(DOCUMENTS[path]) + '$'}}
    judgment = evaluate_navigation(contract, page, site_origin=site_origin)
    checks = dict(judgment['checks'])
    if judgment['status'] == 'unknown':
        raise ValueError('Incomplete native public page capture')
    # A correctly captured wrong object has a reliable failed identity check.
    if judgment['status'] == 'failure':
        return checks
    try:
        content = document_content(page.get('document_body', page['body']), path)
        checks.update(complete_native_content=digest(content) == reference['content_sha256'],
                      complete_content_exposed_in_ax=full_text_exposed(content, page['native_ax']))
    except (KeyError, ValueError, TypeError):
        checks.update(complete_native_content=False, complete_content_exposed_in_ax=False)
    return checks


def navigation_checks(kind, page, site_origin, *, expected_center=None):
    paths = {'home': ('/', r'OpenStreetMap'), 'upload_form': ('/traces/new', r'^Upload GPS Trace$'),
             'export_area': ('/export', r'^Export$')}
    if kind not in paths:
        raise ValueError('Unsupported public Map navigation capability')
    path, heading = paths[kind]
    contract = {'domain': 'map', 'completion': {'path_regex': re.escape(path) + ('?' if path == '/' else '/?'),
                                               'heading_regex': heading}}
    judgment = evaluate_navigation(contract, page, site_origin=site_origin)
    checks = dict(judgment['checks'])
    if judgment['status'] == 'unknown':
        raise ValueError('Incomplete native navigation capture')
    if judgment['status'] == 'failure':
        return checks
    if kind == 'upload_form':
        from .visible_form import form_checks
        checks.update(form_checks(UPLOAD_FORM, page.get('visible_forms')))
    else:
        from .map_view import native_zoom
        try:
            native_zoom(page.get('native_view'))
            checks['native_map_ready'] = True
        except (TypeError, ValueError, KeyError):
            checks['native_map_ready'] = False
        if kind == 'export_area':
            from .map_panel import panel_checks
            checks.update(panel_checks({'kind': 'export_form'}, page.get('map_panel')))
            if expected_center is None:
                raise ValueError('Named-area export needs the preserved initial geographic reference')
            checks['original_area_preserved'] = same_center(expected_center, geo_triplet(page['native_view']))
    return checks


def share_checks(page, expected_center, site_origin):
    """Verify visible native long/short links against an independent reference.

    expected_center is computed from the original native baseline and the
    independently validated sidebar projection, never from a filled input.
    """
    required = ('url', 'http_status', 'login_page', 'error_page')
    if (not isinstance(page, dict) or any(k not in page for k in required) or
            type(page['http_status']) is not int or type(page['login_page']) is not bool or
            type(page['error_page']) is not bool):
        raise ValueError('Incomplete actual Share page capture')
    p = urlsplit(page['url'])
    checks = {'correct_site': origin(page['url']) == origin(site_origin),
              'page_valid': 200 <= page['http_status'] < 300 and not page['login_page'] and not page['error_page'],
              'native_map_page': p.path in ('/', '/search', '/directions', '/export')}
    if not all(checks.values()):
        return checks
    state = page.get('share')
    if not isinstance(state, dict):
        raise ValueError('Native Share state was not captured')
    checks['visible_share_panel'] = state.get('visible') is True
    if not checks['visible_share_panel']:
        return checks
    z, lat, lon = expected_center
    native_geo_uri(z, lat, lon)  # validate independent reference
    try:
        long_url = local_target(site_origin, state['long_value'], '/')
        native_url = local_target(site_origin, state['long_href'], '/')
        long = map_triplet(long_url)
        expected_short = site_origin.rstrip('/') + short_path(z, lat, lon)
        short_url = state['short_value']
        checks.update(long_matches_noneditable_native_link=long_url == native_url,
                      link_retains_original_native_view=same_center(expected_center, long),
                      short_matches_noneditable_native_link=short_url == state['short_href'],
                      short_matches_independent_encoder=short_url == expected_short,
                      geographic_uri_matches_projection=state['geo_uri'] == native_geo_uri(z, lat, lon),
                      link_fields_were_visible=state.get('long_visible') is True and state.get('short_visible') is True)
    except (KeyError, ValueError, TypeError):
        checks['native_link_output_complete'] = False
    return checks


def summarize_controls(controls):
    """A capability pass requires one actual positive plus all actual negatives."""
    names = ('positive', 'wrong_object', 'error_page', 'login_page', 'no_op')
    return (set(names) <= set(controls) and
            all(controls[name].get('passed') is True for name in names))


def independent_cycles(cycles):
    """No admission side effect; only verify complete private controls and reset."""
    if len(cycles) != 2 or {r.get('cycle_index') for r in cycles} != {0, 1}:
        return False
    if not all(r.get('protected_state_unchanged') is True for r in cycles):
        return False
    if not cycles[0].get('initial_fingerprint') or cycles[0]['initial_fingerprint'] != cycles[1].get('initial_fingerprint'):
        return False
    if any(r.get('actor_attempts') != 0 or r.get('api_calls') != 0 or r.get('task_admissions') != 0 for r in cycles):
        return False
    rows = [{r['source_task_id']: r for r in c.get('sources', [])} for c in cycles]
    return (bool(rows[0]) and rows[0].keys() == rows[1].keys() and
            all(row.get('passed') is True and row.get('training_eligible') is False and
                row.get('status') == 'capability_verified' and
                summarize_controls(row.get('controls', {})) for group in rows for row in group.values()))


def wait_current_native_view(page, *, timeout=20000):
    """Wait for public map readiness without inventing an expected center.

    A native home link may contain no fragment. Its map initialization is still
    valid, and a navigation-only goal has no prescribed zoom or center.
    """
    import time
    from playwright.sync_api import TimeoutError as BrowserTimeout
    from .map_view import READINESS, read_map_view, native_zoom
    path = urlsplit(page.url).path
    if path not in ('/', '/export'):
        raise ValueError('Current public home/export map required')
    end = time.monotonic() + timeout / 1000
    args = {'search': False, 'directions': False, 'routeRequest': False,
            'expectedZoom': None, 'expectedCenter': None, 'centerTolerance': 0}
    previous, since = None, None
    while time.monotonic() < end:
        state = page.evaluate(READINESS, args)
        pending = page.evaluate("() => !!(window.jQuery && jQuery.active > 0)")
        signal = state, pending
        now = time.monotonic()
        if signal != previous or not state['ready'] or pending:
            previous, since = signal, now
        elif since is not None and now - since >= .75:
            view = read_map_view(page)
            native_zoom(view)
            return view
        page.wait_for_timeout(min(100, max(1, (end-time.monotonic())*1000)))
    error = BrowserTimeout('Native public map did not settle within its observation budget')
    error.last_native_view = read_map_view(page)
    error.last_native_readiness = page.evaluate(READINESS, args)
    raise error


def search_area_reference(site, page, original_start, initial_view):
    """Check actual first search identity against the independent local snapshot.

    The native geocoder auto-fits its first result. The recorded fragment is an
    initialization input, not a demand to prevent that behavior. No target ID,
    guessed center, pan or zoom is supplied to the browser.
    """
    import json
    import urllib.request
    from urllib.parse import urlencode
    from .map_place_identity import bounds, identity, public_result_matches
    from .map_view import native_zoom
    requested = urlsplit(original_start)
    query = parse_qs(requested.query, keep_blank_values=True).get('query', [])
    current = urlsplit(page.url)
    if (requested.path != '/search' or len(query) != 1 or not query[0].strip() or
            current.path != '/search' or parse_qs(current.query).get('query') != query):
        raise ValueError('Original named search query changed')
    public = page.evaluate(r"""() => ({
      query:document.querySelector('input[name="query"]')?.value,
      results:[...document.querySelectorAll('li.search_results_entry a.set_position')]
        .filter(e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden')
        .map(e=>({path:e.getAttribute('href'),text:e.innerText,
          attributes:Object.fromEntries([...e.attributes].filter(a=>a.name.startsWith('data-')).map(a=>[a.name,a.value]))}))
    })""")
    if public['query'] != query[0] or not public['results']:
        raise ValueError('Native named-area search result is missing')
    with urllib.request.urlopen(site.search_url + '/search?' + urlencode(
            {'q': query[0], 'format': 'jsonv2', 'limit': 20}), timeout=30) as response:
        independent = json.load(response)
    matches = [r for r in independent if public_result_matches(r, public['results'][0])]
    if len(matches) != 1:
        raise ValueError('Native first result differs from independent local geographic data')
    reference = matches[0]
    south, north, west, east = bounds(reference)
    native_zoom(initial_view)
    z, lat, lon = geo_triplet(initial_view)
    precision = math.ceil(math.log2(z))
    tolerance = .5 * 10 ** -precision + 1e-8
    if not (south-tolerance <= lat <= north+tolerance and west-tolerance <= lon <= east+tolerance):
        raise ValueError('Native fitted search map is outside its first result')
    return {'query': query[0], 'identity': dict(zip(('type', 'id'), identity(reference))),
            'reference': reference, 'public_first_result': public['results'][0],
            'native_initial_center': [z, lat, lon], 'native_fit_bounds_allowed': True,
            'geographic_data_source': 'independent_local_snapshot_search',
            'paid_api_calls': 0}
