"""Verify a declared initial route when the native form has become hidden.

This is an initialization check, never a task reward. Evidence comes from the
browser's actual response and a separate read of the leased routing backend.
No navigation, input changes or suggested actor actions are performed.
"""
import json
from urllib.request import urlopen

from .map_route_initialization_binding import initial_url_state
from .map_route_normal_capture import complete_route, exact_pair, fingerprint


def verify_initial_response(start_path, state, served, independent_body):
    pair, mode = initial_url_state(start_path)
    if (not isinstance(served, dict) or served.get('complete_native_response') is not True
            or served.get('http_status') != 200 or served.get('profile') != mode
            or not exact_pair(served.get('pair'), pair)):
        raise ValueError('Initial native request endpoints or mode differ')
    route = complete_route(independent_body)
    complete_route(served.get('body'))
    if fingerprint(served['body']) != fingerprint(independent_body):
        raise ValueError('Initial browser response differs from native backend')
    rows = state.get('rows')
    if (state.get('route_visible') is not True or state.get('loading') is not False
            or not isinstance(rows, list) or not rows
            or any(not isinstance(row, str) or not row.strip() for row in rows)
            or len(rows) != len(route['legs'][0]['steps'])
            or not isinstance(state.get('summary'), str) or not state['summary'].strip()):
        raise ValueError('Initial native route is incomplete on the page')
    return dict(profile=mode, pair=pair, body_sha256=fingerprint(independent_body),
                response_index=served['response_index'], rendered_rows=len(rows),
                checks_scope='initial_request_and_rendering_only_not_task_success')


def read_independent_initial(site, start_path):
    pair, mode = initial_url_state(start_path)
    coords = ';'.join(str(lon)+','+str(lat) for lat, lon in pair)
    url = site.route_urls[mode]+'/route/v1/driving/'+coords+'?overview=false&steps=true'
    with urlopen(url, timeout=20) as response:
        if response.status != 200:
            raise ValueError('Initial native backend is unavailable')
        body = json.load(response)
    complete_route(body)
    return body
