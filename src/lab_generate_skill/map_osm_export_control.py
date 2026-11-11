"""Private CPU export controls; never imported by actor action policy."""
import re
from urllib.parse import urlsplit, parse_qs


def submit_state(page):
    target = page.locator('form.export_form #export_commit input[type=submit]:visible')
    count = target.count()
    if count != 1: raise ValueError('Exactly one visible native Export submit is required')
    return {'visible': target.is_visible(), 'enabled': target.is_enabled(),
            'disabled_attribute_present': target.get_attribute('disabled') is not None,
            'native_disable_with': target.get_attribute('data-disable-with'),
            'native_ujs_disabled': target.get_attribute('data-ujs-disabled'),
            'native_control_count': count}


def fresh_document(page, site_origin, *, waiter, timeout=15000):
    """Fresh actual native form after an attachment leaves UJS disabled state.

    Use only the currently observed local Export URL and preserve its native
    map view. Do not remove disabled attributes, dispatch invented submit
    events, alter a field, force a click or select a different source start.
    """
    original_url = page.url; current = urlsplit(original_url); origin = urlsplit(site_origin)
    values = parse_qs(current.fragment, strict_parsing=True, keep_blank_values=True)
    if ((current.scheme, current.netloc) != (origin.scheme, origin.netloc) or current.path != '/export' or
        current.username or current.password or current.query or set(values) != {'map'} or
        len(values['map']) != 1 or not re.fullmatch(r'\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?', values['map'][0])):
        raise ValueError('An actually observed same-origin native Export map document is required')
    before = waiter(page)
    if not isinstance(before, dict) or not before.get('native_geo_uri'):
        raise ValueError('Native pre-download map view must be observed')
    original_submit = submit_state(page)
    # goto of the same URL can be a no-op/hash navigation. Explicit reload
    # creates the fresh native document while retaining the observed URL.
    response = page.reload(wait_until='domcontentloaded', timeout=timeout)
    if response is None or response.status != 200: raise ValueError('Fresh native Export document unavailable')
    after = waiter(page)
    if after.get('native_geo_uri') != before['native_geo_uri']:
        raise ValueError('Fresh native form changed the observed map view')
    refreshed_submit = submit_state(page)
    if refreshed_submit['enabled'] is not True: raise ValueError('Fresh native Export form is still disabled')
    return {'actual_document_navigation': True, 'observed_path': current.path, 'native_map_view_preserved': True,
            'original_submit': original_submit, 'fresh_submit': refreshed_submit,
            'force_enable': False, 'force_click': False, 'original_actor_start_changed': False}
