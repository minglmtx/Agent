"""Terminal-only route scoring against independently established references.

References are private admission artifacts. This module never resolves a new
target from actor output or treats temporary exploration as task failure.
"""
from urllib.parse import urlsplit

from .map_route_normal_capture import complete_route, exact_pair, fingerprint
from .map_candidate_route_controls import evaluate_rendered_candidate

VERSION = 'map-candidate-native-route-terminal-v1'


def evaluate_terminal(references, *, page, state, served, site_origin,
                      runtime_error=None, capture_error=None, integrity=True):
    checks = {}
    def result(status, reason):
        return dict(version=VERSION, status=status,
                    reward={'success': 1., 'failure': 0., 'unknown': None}[status],
                    checks=checks, reason=reason)
    if not isinstance(references, list) or not references:
        raise ValueError('Independent admitted route references required')
    for ref in references:
        if not exact_pair(ref.get('pair'), ref.get('pair')) or ref.get('profile') not in ('car','bike','foot'):
            raise ValueError('Reference endpoints and mode required')
        complete_route(ref['body'])
        if not isinstance(ref.get('reference_state'),dict):
            raise ValueError('Independently rendered reference required')
    if runtime_error or capture_error or integrity is not True:
        return result('unknown', 'Runtime, capture or state-integrity verification unavailable.')
    if (not isinstance(page,dict) or not isinstance(page.get('url'),str)
            or type(page.get('http_status')) is not int
            or any(type(page.get(k)) is not bool for k in ('login_page','error_page'))):
        return result('unknown', 'Incomplete terminal document capture.')
    status = page['http_status']
    if status < 200 or status >= 500:
        return result('unknown', 'Terminal document transport or server error.')
    actual, expected = urlsplit(page['url']), urlsplit(site_origin)
    checks.update(correct_site=(actual.scheme,actual.netloc)==(expected.scheme,expected.netloc),
                  page_valid=200<=status<300 and not page['login_page'] and not page['error_page'])
    if not all(checks.values()):
        return result('failure', 'Final document is not a valid local task page.')
    if (not isinstance(state,dict) or any(type(state.get(k)) is not bool for k in ('route_visible','loading'))
            or not isinstance(state.get('rows'),list)):
        return result('unknown', 'Native route observation unavailable.')
    if state['loading']:
        return result('unknown', 'Native routing was still pending at termination.')
    checks['route_line_displayed'] = state['route_visible']
    checks['route_instructions_displayed'] = bool(state['rows'])
    if not all(checks.values()):
        return result('failure', 'No completed route is displayed at termination.')
    if not isinstance(served,dict) or served.get('complete_native_response') is not True:
        return result('unknown', 'Displayed route lacks complete native response evidence.')
    try:
        complete_route(served['body'])
    except (KeyError,ValueError,TypeError):
        return result('unknown', 'Captured native response is incomplete.')
    matches = [r for r in references if exact_pair(r['pair'],served.get('pair'))
               and r['profile']==served.get('profile')]
    checks['requested_endpoints_and_mode'] = bool(matches)
    if not matches:
        return result('failure', 'Final route does not match the declared endpoints and mode.')
    if not any(fingerprint(r['body'])==fingerprint(served['body']) for r in matches):
        return result('unknown', 'Native routing data differs from the validated reference.')
    outcomes = []
    try:
        for r in matches:
            if fingerprint(r['body'])!=fingerprint(served['body']):
                continue
            outcomes.append(evaluate_rendered_candidate(r['pair'],r['profile'],r['body'],
                r['reference_state'],served,state,page['url'],endpoint_labels=r.get('endpoint_labels')))
    except (ValueError,TypeError,KeyError):
        return result('unknown', 'Native rendered route capture is incomplete.')
    winner = next((r for r in outcomes if all(r.values())),None)
    # Do not combine individual passing conditions from different alternatives.
    checks.update(winner if winner is not None else outcomes[0])
    return result('success' if winner is not None else 'failure',
                  'Final native route checked against one complete independent reference.')


def feedback(judgment):
    if judgment.get('version')!=VERSION:
        raise ValueError('Route terminal judgment required')
    return dict(status=judgment['status'], reward=judgment['reward'],
                checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items() if type(v)is bool],
                private_reference_values_provided=False, action_sequence_provided=False)
