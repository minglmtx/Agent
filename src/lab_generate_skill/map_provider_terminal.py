"""Terminal-only scoring for the frozen native map-provider environment.

Environment/control admission is separate. These functions do not authorize an
actor attempt, choose actions, or expose private provider byte references.
"""
from urllib.parse import urlsplit
import math
from .map_frozen_provider_runtime import provider_checks

from .map_provider_contract import PROVIDER_CODES

VERSION = 'map-frozen-provider-terminal-v1'


def evaluate_provider_terminal(spec, *, initial, terminal, page, site_origin,
                               server, response_hashes, initial_route=None,
                               terminal_route=None, runtime_error=None,
                               integrity=True, capture_error=None):
    if (spec.get('family') != 'base_layer' or spec.get('provider') not in PROVIDER_CODES
            or type(spec.get('retain_initial_route')) is not bool
            or type(spec.get('retain_initial_area', True)) is not bool):
        raise ValueError('Explicit native provider completion contract required')
    checks = {}
    def result(status, reason):
        return dict(version=VERSION, status=status,
                    reward={'success': 1., 'failure': 0., 'unknown': None}[status],
                    checks=checks, reason=reason)
    if runtime_error or capture_error or integrity is not True:
        return result('unknown', 'Runtime, capture or state-integrity verification unavailable.')
    required = ('url', 'http_status', 'login_page', 'error_page')
    if (not isinstance(page, dict) or any(k not in page for k in required)
            or not isinstance(page['url'], str) or type(page['http_status']) is not int
            or type(page['login_page']) is not bool or type(page['error_page']) is not bool):
        return result('unknown', 'Incomplete terminal document capture.')
    status = page['http_status']
    if status < 200 or status >= 500:
        return result('unknown', 'Terminal document transport or server error.')
    actual, expected = urlsplit(page['url']), urlsplit(site_origin)
    checks.update(correct_site=(actual.scheme, actual.netloc) == (expected.scheme, expected.netloc),
                  page_valid=200 <= status < 300 and not page['login_page'] and not page['error_page'])
    if not all(checks.values()):
        return result('failure', 'Terminal document is not a valid local map page.')
    if not isinstance(initial, dict) or not isinstance(terminal, dict):
        return result('unknown', 'Native initial or terminal map observation unavailable.')
    try:
        # Validate the observation shape before interpreting a missing field as
        # a legitimate negative result from the lower-level predicate.
        for state in (initial, terminal):
            if (type(state['zoom']) is not int or not isinstance(state['active'], list)
                    or not 0 <= state['zoom'] <= 20
                    or not all(type(state['size'][k]) in (int, float) and
                               math.isfinite(state['size'][k]) and state['size'][k] > 0 for k in ('x', 'y'))
                    or not all(type(state['center'][k]) in (int, float) and
                               math.isfinite(state['center'][k]) for k in ('lat', 'lng'))):
                raise ValueError('Malformed native map state')
            for layer in state['active']:
                if (not isinstance(layer['code'], str) or not isinstance(layer['template'], str)
                        or not isinstance(layer['tiles'], list)):
                    raise ValueError('Malformed native layer')
                for tile in layer['tiles']:
                    if (type(tile['loaded']) is not bool or type(tile['current']) is not bool
                            or not isinstance(tile['src'], str) or len(tile['rect']) != 4
                            or not all(type(v) in (int, float) and math.isfinite(v) for v in tile['rect'])
                            or not all(type(tile['coords'][k]) is int for k in ('z', 'x', 'y'))):
                        raise ValueError('Malformed native tile')
        native = provider_checks(initial, terminal, spec['provider'], server, response_hashes)
    except (KeyError, TypeError, ValueError):
        return result('unknown', 'Incomplete native provider observation.')
    checks.update(native)
    if not spec.get('retain_initial_area', True):
        checks.pop('same_initial_area')
    checks['requested_layer_selected'] = [layer['code'] for layer in terminal['active']] == [
        PROVIDER_CODES[spec['provider']]]
    area_satisfied = not spec.get('retain_initial_area', True) or native['same_initial_area']
    if not checks['requested_layer_selected'] or not area_satisfied:
        return result('failure', 'Requested layer or required original map area is not displayed.')
    if not native['native_requested_layer']:
        return result('unknown', 'Selected provider transport does not match the verified environment.')
    if spec['retain_initial_route']:
        if not isinstance(initial_route, dict) or not isinstance(terminal_route, dict):
            return result('unknown', 'Initial or terminal route capture unavailable.')
        required_route = ('route_visible', 'loading', 'origin', 'destination', 'engine', 'rows')
        if any(k not in r for r in (initial_route, terminal_route) for k in required_route):
            return result('unknown', 'Incomplete native route capture.')
        if terminal_route['loading']:
            return result('unknown', 'Native route still loading at termination.')
        checks['route_retained'] = (terminal_route['route_visible'] is True and
            all(terminal_route[k] == initial_route[k] for k in ('origin', 'destination', 'engine', 'rows')))
        if not checks['route_retained']:
            return result('failure', 'Required initial route is not retained at termination.')
    # Blank, unavailable or changed provider bytes can be an environment or
    # response-capture failure. A checkbox alone is not proof of completion,
    # and lack of image evidence must not become a negative training reward.
    if not native['loaded_genuine_tiles'] or not native['complete_visible_coverage']:
        return result('unknown', 'Requested provider image bytes or visible coverage are not verified.')
    return result('success', 'Requested native layer, original area and required route are verified.'
                  if spec.get('retain_initial_area', True) else
                  'Requested native layer and declared route requirements are verified.')


def feedback(judgment):
    if judgment.get('version') != VERSION:
        raise ValueError('Provider terminal judgment required')
    return dict(status=judgment['status'], reward=judgment['reward'],
                checks=[dict(condition=k, passed=v) for k, v in judgment['checks'].items() if type(v) is bool],
                private_reference_values_provided=False, action_sequence_provided=False)
