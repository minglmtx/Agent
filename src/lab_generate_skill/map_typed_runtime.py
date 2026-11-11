"""Optional typed Map runtime adapter, isolated from shared query dispatch.

No execution strategy, hidden expected value or evaluator state is appended to
actor observations. Share state is a private read-only timeline tied to issued
observations. Full ordinary admissions remain authoritative; task-specific
cycle views only simplify runtime reset checks and cannot grant admission.
"""
import copy
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .io_utils import atomic_write_json

FAMILY = 'map_typed_native'
VERSION = 'map-typed-runtime-v1'


def _typed():
    # Import lazily so a shared query dispatcher can import this adapter without
    # entering map_typed -> site_query_rules -> adapter recursively at startup.
    from . import map_typed_information_share
    return map_typed_information_share


def family(contract):
    query = contract.get('query', {})
    marker = query.get('family') if isinstance(query, dict) else None
    typed = contract.get('map_typed')
    if marker == FAMILY or typed is not None:
        if contract.get('domain') != 'map' or marker != FAMILY or not isinstance(typed, dict):
            raise ValueError('Typed Map marker and query family must agree')
        return FAMILY
    return None


def validate(contract):
    if family(contract) != FAMILY:
        raise ValueError('Expected a typed Map query contract')
    q = _typed().validate(contract)
    allowed = ('kind', 'fields', 'field_meanings', 'record_fields', 'minimum_records')
    projection = {'family': FAMILY, **{k: q[k] for k in allowed if k in q}}
    if contract['query'] != projection:
        raise ValueError('Public query projection differs from the typed native protocol')
    if set(q.get('field_meanings', {})) != set(q['fields']) or not all(isinstance(v, str) and v for v in q['field_meanings'].values()):
        raise ValueError('Typed public field meanings must be explicit')
    return q


def generic_query_projection(contract):
    validate(contract)
    result = copy.deepcopy(_typed().query_projection(contract))
    result.pop('map_typed', None)
    result['query'].pop('family', None)
    result['query'].pop('kind', None)
    return result


def public_protocol(contract):
    q = validate(contract)
    # Do not expose reference paths, layouts, file locations, expected centers,
    # native source hashes, source IDs or private reference values.
    return {'goal': contract['goal'], 'fields': copy.deepcopy(q['fields']),
            'field_meanings': copy.deepcopy(q['field_meanings']),
            **{k: copy.deepcopy(q[k]) for k in ('record_fields', 'minimum_records') if k in q},
            'local_link_only': q['kind'] == 'share_link'}


def public_goal(contract):
    validate(contract)
    return _typed().public_goal(contract)


def reference(site, contract):
    validate(contract)
    return _typed().reference(contract, site)


def require_admission(contract, proof):
    validate(contract)
    return _typed().require_admission(contract, proof)


def task_cycle_views(contract, proof):
    require_admission(contract, proof)
    views = []
    for cycle in proof['cycles']:
        rows = [r for r in cycle['tasks'] if r.get('task_id') == contract['task_id']]
        # The gate already checked cardinality; retain a separate explicit
        # assertion so future proof reshaping cannot pick an adjacent task.
        if len(rows) != 1:
            raise ValueError('Exactly one task-specific native cycle row required')
        view = copy.deepcopy(rows[0])
        for key in ('cycle', 'initial_fingerprint', 'final_fingerprint', 'clean_reset_verified', 'dirty_reuse_refused'):
            if key in view and view[key] != cycle[key]:
                raise ValueError('Task-specific row contradicts the native cycle baseline')
            view[key] = copy.deepcopy(cycle[key])
        views.append(view)
    return views


def prepare_site(site, contract, directory, *, browser=None):
    validate(contract)
    from .map_community_fixture import profile_for_contracts
    from .map_native_account_bootstrap import initialize_native_account
    profile = profile_for_contracts([contract], 'map')
    if profile is None or getattr(site, 'community_fixture', None) != profile:
        raise ValueError('Typed runtime requires its explicitly declared local native profile')
    existing = getattr(site, '_native_navigation_account_baseline', None)
    if existing is not None:
        site.reset_guard.require_unchanged()
        proof = dict(existing, verified_clean_reuse=True)
    elif browser is not None:
        proof = initialize_native_account(site, browser=browser)
        site._native_navigation_account_baseline = proof
    else:
        # BrowserGym already owns the synchronous manager inside actor workers.
        # Borrow it; do not start/stop another sync_playwright context manager.
        from browsergym.core.env import _get_global_playwright
        owned = _get_global_playwright().chromium.launch(headless=True)
        try:
            proof = initialize_native_account(site, browser=owned)
        finally:
            owned.close()
        site._native_navigation_account_baseline = proof
    atomic_write_json(Path(directory) / 'typed-native-account-initialization.json', proof)
    return reference(site, contract)


def observe_initial(page, contract, proof, directory):
    validate(contract); admitted = task_cycle_views(contract, proof)[0]
    original = urlsplit(contract['start_path']); current = urlsplit(page.url)
    if current.path != original.path or current.query != original.query:
        raise RuntimeError('Typed runtime initial document differs from the original first start')
    view = None
    if original.path in ('/', '/search', '/directions'):
        from .map_view import wait_native_view
        view = wait_native_view(page, contract['start_path'])
        expected = admitted.get('initial_native_view')
        if not isinstance(expected, dict) or view.get('native_geo_uri') != expected.get('native_geo_uri'):
            raise RuntimeError('Typed runtime initial view differs from both fresh native controls')
    state = {'version': VERSION, 'original_start_path': contract['start_path'],
             'original_initial_view_verified': True, 'native_view': view,
             'private_reference_added_to_actor': False}
    atomic_write_json(Path(directory) / 'initial-typed-native-view.json', state)
    return state


def safe_map_url(value):
    if not isinstance(value, str):
        return None
    try:
        p = urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password:
            return None
        if p.path.startswith('/go/'):
            if p.query or p.fragment or not re.fullmatch(r'/go/[A-Za-z0-9_~\-]+', p.path):
                return None
        elif p.path == '/':
            values = parse_qs(p.fragment, keep_blank_values=True, strict_parsing=True)
            if p.query or set(values) not in ({'map'}, {'map', 'layers'}) or any(len(v) != 1 for v in values.values()):
                return None
            if not re.fullmatch(r'\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?', values['map'][0]):
                return None
            if 'layers' in values and not re.fullmatch(r'[A-Za-z]+', values['layers'][0]):
                return None
        else:
            return None
    except (ValueError, KeyError):
        return None
    return value


def share_projection(state):
    """Persist only whitelisted native artifact fields, never raw OAuth DOM."""
    if not isinstance(state, dict) or type(state.get('visible')) is not bool:
        raise ValueError('Missing native Share capture')
    result = {'visible': state['visible']}
    for name in ('map_visible', 'long_visible', 'short_visible'):
        if name in state and type(state[name]) is bool:
            result[name] = state[name]
    for name in ('base_control_count', 'overlay_control_count'):
        if name in state and type(state[name]) is int and 0 <= state[name] <= 1000:
            result[name] = state[name]
    for name in ('active_base_labels', 'checked_base_labels', 'active_overlay_labels'):
        if isinstance(state.get(name), list) and all(isinstance(v, str) and len(v) <= 256 for v in state[name]):
            result[name] = list(state[name])
    for name in ('long_href', 'short_href', 'long_value', 'short_value'):
        if name in state:
            result[name] = safe_map_url(state[name])
    return result


class ShareTimeline:
    def __init__(self, contract, directory):
        q = validate(contract)
        self.contract = copy.deepcopy(contract)
        self.enabled = q['kind'] == 'share_link'
        self.path = Path(directory) / 'private-typed-share-observations.json'
        self.records = []
        if self.enabled:
            if self.path.exists():
                raise ValueError('Keep the existing private Share timeline; do not clear an attempt')
            self.save()

    def save(self):
        atomic_write_json(self.path, {'version': VERSION, 'contract_fingerprint': _typed().fingerprint(self.contract),
                         'samples': self.records, 'read_only': True, 'private_reference_added_to_actor': False,
                         'clipboard_access': False, 'external_delivery': False})

    def record(self, page, *, event='issued_observation'):
        if not self.enabled:
            return None
        if event not in ('issued_observation', 'terminal'):
            raise ValueError('Share samples must follow an issued observation or terminal capture')
        state = share_projection(_typed().read_share_state(page))
        self.records.append({'sequence': len(self.records), 'event': event, 'state': state})
        self.save()
        return copy.deepcopy(state)

    def states(self):
        return [copy.deepcopy(r['state']) for r in self.records]


def load_share_timeline(contract, directory):
    validate(contract)
    path = Path(directory) / 'private-typed-share-observations.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if (value.get('version') != VERSION or value.get('contract_fingerprint') != _typed().fingerprint(contract) or
            value.get('read_only') is not True or value.get('private_reference_added_to_actor') is not False):
        raise ValueError('Private native Share timeline does not match this typed task')
    rows = value.get('samples')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Malformed private Share sample timeline')
    states = []
    for sequence, row in enumerate(rows):
        if row.get('sequence') != sequence or row.get('event') not in ('issued_observation', 'terminal'):
            raise ValueError('Private Share samples are out of order or unsupported')
        projected = share_projection(row.get('state'))
        if projected != row['state']:
            raise ValueError('Unexpected private Share capture fields')
        states.append(projected)
    return states


def evaluate(contract, page, answer, initial, final, *, site_origin, observations=None, runtime_error=None):
    q = validate(contract)
    if q['kind'] == 'share_link':
        return _typed().evaluate(contract, page, answer, initial, final, site_origin=site_origin,
                                 observations=observations, runtime_error=runtime_error)
    if runtime_error:
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': 'Environment or inference error'}
    if initial != _typed().reference(contract):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': 'Native initial reference differs from pinned documents'}
    from .site_query_rules import evaluate_query
    # Neither marker remains: optional family dispatch can safely delegate back
    # to the unchanged generic text/record evaluator exactly once.
    return evaluate_query(generic_query_projection(contract), page, answer, initial, final,
                          site_origin=site_origin, runtime_error=runtime_error)


def feedback(judgment):
    return _typed().feedback(judgment)
