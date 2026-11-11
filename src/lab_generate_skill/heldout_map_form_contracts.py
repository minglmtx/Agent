"""Bind public form-navigation goals; native qualification remains separate.

No account creation or authentication success is inferred. The existing native
form evaluator supplies the completion contract; this module only binds source
identity, the selected original first frame, and the public navigation scope.
"""
import re
from urllib.parse import urlsplit

from .authentication_page import completion
from .heldout_initial_state import fingerprint


FORM_GOALS = {
    'Navigate to the login page to access your OpenStreetMap account': 'login',
    'Navigate to the Sign Up page to create a new OpenStreetMap account': 'signup',
}
TARGET_PATHS = {'login': '/login', 'signup': '/user/new'}


def candidate(row, frame):
    """A private draft from one previously selected, unmodified source frame."""
    kind = FORM_GOALS.get(row.get('goal'))
    if kind is None:
        return None
    sid = row.get('source_task_id')
    if (not isinstance(sid, str) or not re.fullmatch('[0-9a-f]{20}', sid)
            or row.get('domain') != 'map' or row.get('split') != 'test'
            or row.get('provenance_status') != 'first_frame_bound' or row.get('blockers') != []):
        raise ValueError('Unblocked original heldout Map identity required')
    start = row.get('start_path')
    if not isinstance(start, str) or not start.startswith('/') or start.startswith('//'):
        raise ValueError('Original local start path required')
    parsed = urlsplit(start)
    if parsed.scheme or parsed.netloc:
        raise ValueError('Original local start path required')
    for key in ('baseline_fingerprint', 'initial_observation_sha256'):
        if not isinstance(row.get(key), str) or not re.fullmatch('[0-9a-f]{64}', row[key]):
            raise ValueError('Original source fingerprints required')
    observation = frame.get('observation')
    if not isinstance(observation, dict) or not isinstance(observation.get('axtree'), str):
        raise ValueError('Original first frame requires its recorded AX observation')
    original = urlsplit(frame.get('original_url', ''))
    original_path = (original.path or '/') + ('?' + original.query if original.query else '')
    original_path += '#' + original.fragment if original.fragment else ''
    if (frame.get('source_task_id') != sid or frame.get('trace_id') != row.get('selected_trace_id')
            or frame.get('start_path') != start
            or original.scheme not in ('http', 'https') or not original.netloc
            or original.username or original.password or original_path != start
            or frame.get('observation_sha256') != row['initial_observation_sha256']
            or fingerprint(observation) != row['initial_observation_sha256']):
        raise ValueError('Selected original first frame differs from source identity or start')
    result = dict(task_id=sid, source_task_id=sid, split='test', domain='map', goal=row['goal'],
        start_path=start, task_text_changed=False, selected_trace_id=row['selected_trace_id'],
        initial_observation_sha256=row['initial_observation_sha256'],
        selected_first_frame_sha256=fingerprint(frame),
        baseline_fingerprint=row['baseline_fingerprint'], completion=completion(kind),
        control_target_path=TARGET_PATHS[kind], wrong_target_path='/help', verify_url_only=True,
        allow_initial_success=parsed.path.rstrip('/') == TARGET_PATHS[kind],
        binding_family='heldout_map_form_navigation', heldout_quarantine=True,
        eligible_for_training=False, purpose='codebase_acceptance', formal_test_metric=False,
        evaluation_ready=False, original_initial_state_equivalence='unverified',
        status='draft_requires_native_initialization_controls_and_reset',
        completion_scope='The requested native form is displayed; no login or account creation is required.',
        pending=['source_bound_native_initial_state_and_authentication',
                 'native_form_and_wrong_target_hidden_form_url_only_error_controls',
                 'two_independent_initial_reset_cycles_and_full_protection',
                 'actual_public_request_isolation', 'one_actual_actor_attempt', 'independent_review'])
    result['engineering_contract_sha256'] = fingerprint(result)
    return result
