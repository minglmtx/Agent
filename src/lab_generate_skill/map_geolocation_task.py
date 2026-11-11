"""Local device-location task protocol, independent of actor action selection.

The browser supplies a deterministic local location. This is a versioned
environment fixture, not a reconstruction of the original recording's device.
"""
from urllib.parse import urlsplit
from .map_geolocation import validate_fixture, geolocation_checks
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'map-local-device-location-v1'
ADMISSION_VERSION = VERSION + '-admission'
CASES = {'no_op': 'failure', 'positive': 'success', 'wrong_location': 'failure',
         'url_only': 'failure', '404': 'failure', 'login': 'failure'}


def validate(c):
    spec = c.get('map_geolocation')
    if c.get('domain') != 'map' or not isinstance(spec, dict) or set(spec) != {'fixture', 'fixture_version'}:
        raise ValueError('Explicit local browser location fixture required')
    validate_fixture(spec['fixture'])
    if spec['fixture_version'] != VERSION:
        raise ValueError('Unknown local device fixture version')
    u = urlsplit(c['start_path'])
    if u.scheme or u.netloc or u.path not in ('/', '/help'):
        raise ValueError('Unsupported original location-task start')
    if u.path == '/':
        from .map_metadata_query import initial_view
        initial_view(c['start_path'])


def fingerprint(c):
    return reference_fingerprint({k: c.get(k) for k in (
        'task_id', 'source_task_id', 'domain', 'goal', 'start_path',
        'map_geolocation', 'heldout_quarantine', 'start_revision', 'goal_revision')})


def configure_context(context, c, origin):
    validate(c)
    context.set_geolocation(c['map_geolocation']['fixture'])
    context.grant_permissions(['geolocation'], origin=origin)


def evaluate(c, page, state, *, site_origin, runtime_error=None):
    validate(c)
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Environment or inference error')
    if (not isinstance(page, dict) or type(page.get('http_status')) is not int
            or not 200 <= page['http_status'] < 500):
        return unknown('Missing terminal page or transport/server error')
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin)}
    if checks['page_valid']:
        try:
            if 'requesting' in state.get('control_classes', []):
                return unknown('Native browser location request still pending')
            checks.update(geolocation_checks(c['map_geolocation']['fixture'], state))
        except (ValueError, TypeError, AttributeError):
            return unknown('Missing native location-control capture')
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure',
            'reward': float(passed), 'checks': checks, 'reason': None}


def feedback(j):
    meanings = {
        'page_valid': 'The final document is a valid page on the task website.',
        'native_location_active': 'The native device-location feature is active and has completed its request.',
        'map_center_matches_location': 'The map center matches the configured browser device location.',
        'native_map_rendered': 'The native map and its tiles are displayed.'}
    return {'status': j['status'], 'reward': j['reward'], 'reason': j.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': meanings[k]} for k, v in j['checks'].items()],
            'action_sequence_provided': False, 'reference_values_provided': False}


def require_admission(c, proof):
    validate(c)
    if (c.get('heldout_quarantine') or proof.get('admission_version') != ADMISSION_VERSION
            or proof.get('contract_fingerprint') != fingerprint(c)):
        raise ValueError('Quarantined or stale geolocation admission')
    cycles = proof.get('cycles', [])
    if (not proof.get('passed') or len(cycles) != 2
            or proof.get('reset_mode') != 'independent_full_geographic_deployments'):
        raise ValueError('Two independent full native deployments required')
    for row in cycles:
        if (not row.get('passed') or row.get('checks') != CASES or not row.get('full_reset_verified')
                or not row.get('wrong_location_control_valid') or not row.get('initial_fingerprint')
                or row['initial_fingerprint'] != row.get('final_fingerprint')):
            raise ValueError('Incomplete native geolocation controls/reset')
    if cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint']:
        raise ValueError('Independent device-location baselines disagree')
