"""Explicit same-capability local named-place training revisions.

This mapping is never an original benchmark equivalence or native admission.
Only named endpoint/search parameters change; every mode, completion/readout,
source start, trace, and other original condition stays bound exactly. A reverse
task gets an explicit declared initial route, with actual initial and reversed
native body/rendered proof still required separately by the normal source gate.
"""
from copy import deepcopy
import hashlib, json, re
from pathlib import Path
from .source_revision_binding import binding, require_source_binding
from .map_route_normal_capture import fingerprint, exact_pair, complete_route
from .map_native_identity_declarations import POLICIES, POLICY_SHA, declare_query

from .map_identity_policy_scope import require_compatible_policy

VERSION = 'native-local-coverage-same-capability-derived-v1'
SUFFIX = '--local-coverage-training-v1'
KINDS = {'named_places', 'reverse_named_initial_route', 'named_place_search'}


def public_goal(original, queries):
    request = original.get('endpoint_request', {})
    kind = request.get('kind', original.get('protocol', {}).get('kind'))
    completion = original.get('completion_kind')
    modes = original.get('allowed_modes', [])
    if kind == 'named_place_search':
        instruction = 'Search for ' + queries[0] + ' and view this geographical place on the native map.'
    elif kind == 'reverse_named_initial_route':
        instruction = ('Reverse the explicitly initialized current driving directions from '
                       + queries[0] + ' to ' + queries[1] + '. The resulting route must run from '
                       + queries[1] + ' to ' + queries[0] + ', retaining car mode.')
    elif completion == 'all_turns_displayed' and modes == ['car']:
        instruction = 'View the complete detailed turn-by-turn driving directions from ' + queries[0] + ' to ' + queries[1] + '.'
    elif completion == 'displayed_route' and modes == ['foot']:
        instruction = 'Get walking directions from ' + queries[0] + ' to ' + queries[1] + '.'
    elif completion == 'mode_times' and modes == ['car', 'bike']:
        instruction = 'Compare travel times between car and bicycle routes from ' + queries[0] + ' to ' + queries[1] + '.'
    else:
        raise ValueError('No declared same-capability local training revision for this original operation')
    return (instruction + ' This is an explicit local training derivative with different named geography. '
            + 'The original goal "' + original['goal'] + '", all original starts and traces, and all old scores remain unchanged. '
            + 'It does not claim equivalence to the original geographical task or its benchmark result.')


def _construct(original, queries, initial_pair=None, *, policy_sha256=POLICY_SHA):
    require_compatible_policy(policy_sha256, queries)
    c = deepcopy(original)
    request = c.get('endpoint_request', {})
    kind = request.get('kind', c.get('protocol', {}).get('kind'))
    if kind not in KINDS or any(q not in POLICIES for q in queries):
        raise ValueError('Known exact native named-place policies required')
    if kind == 'named_place_search':
        if len(queries) != 1: raise ValueError('Exactly one named-search target required')
        c['protocol']['query'] = queries[0]
        declaration = c['protocol']['native_identity_declaration']
        declaration.pop('name_in_original_goal', None)
        declaration.update(query=queries[0], name_in_derived_goal=queries[0],
                           identity_policy=deepcopy(POLICIES[queries[0]]), identity_policy_sha256=policy_sha256)
    elif kind == 'named_places':
        if len(queries) != 2 or queries[0] == queries[1]: raise ValueError('Two distinct named route targets required')
        c['endpoint_request']['queries'] = list(queries)
    else:
        if (len(queries) != 2 or queries[0] == queries[1] or c.get('allowed_modes') != ['car']
                or c.get('completion_kind') != 'transformed_route' or initial_pair is None):
            raise ValueError('Reverse retains car transformation and an explicitly declared initial pair')
        from .map_route import route_path
        c['endpoint_request']['initial_queries'] = list(queries)
        c['start_path'] = route_path(initial_pair, 'car')
        c['start_revision'] = {'version': VERSION, 'original_start': original['recorded_start_paths'][0],
            'derived_start': c['start_path'], 'reason': 'Publicly declared native initial route is required for the same reverse operation.',
            'equivalent_to_original_evaluation': False}
        c['initialization_revision'] = dict(original['initialization_revision'], selected_start=c['start_path'], binding_version=VERSION)
        c['local_coverage_initialization'] = {'version': VERSION, 'initial_pair': deepcopy(initial_pair),
            'initial_mode': 'car', 'initial_queries': list(queries), 'actual_independent_initial_reference_required': True}
    goal = public_goal(original, queries)
    c.update(task_id=original['source_task_id'] + SUFFIX, goal=goal, task_text_changed=True,
             is_explicit_derivative=True, original_evaluation_equivalence=False)
    c['goal_revision'] = {'version': VERSION, 'original_goal': original['goal'], 'derived_goal': goal,
        'reason': 'Complete independent native original query has zero semantically matching records; explicitly retain the operation using known local named geography.',
        'equivalent_to_original_goal': False, 'original_contract': deepcopy(original),
        'original_contract_sha256': fingerprint(original), 'derived_queries': list(queries), 'policy_sha256': policy_sha256}
    return c


def derive(original, queries, *, initial_pair=None):
    c = _construct(original, queries, initial_pair)
    validate(c)
    return c


def validate(c):
    binding(c)
    revision = c.get('goal_revision', {})
    original = revision.get('original_contract')
    if (revision.get('version') != VERSION or not isinstance(original, dict)
            or original.get('task_id') != c['source_task_id'] or original.get('source_task_id') != c['source_task_id']
            or original.get('goal') != c.get('original_goal') or original.get('goal_revision')
            or original.get('training_initialization') or original.get('task_text_changed') is not False
            or revision.get('original_contract_sha256') != fingerprint(original)
            or c.get('training_initialization')
            or c.get('original_evaluation_equivalence') is not False):
        raise ValueError('Complete original source and explicit local coverage goal revision required')
    queries = revision.get('derived_queries')
    if not isinstance(queries, list): raise ValueError('Explicit derived native named queries required')
    mapping = c.get('local_coverage_initialization', {})
    expected = _construct(original, queries, mapping.get('initial_pair'), policy_sha256=revision.get('policy_sha256'))
    if {k: v for k, v in c.items() if k != 'admission_result'} != expected:
        raise ValueError('Local derivative changed an undeclared original capability, mode, start, trace, or condition')
    old = original.get('endpoint_request', {}).get('queries', original.get('endpoint_request', {}).get('initial_queries'))
    if old is None: old = [original.get('protocol', {}).get('query')]
    if queries == old: raise ValueError('A local coverage goal revision must explicitly change the named geography')
    return {'original_contract': deepcopy(original), 'derived_queries': deepcopy(queries)}


def require_original_binding(c, controlled, inventory):
    validate(c)
    return require_source_binding(c, controlled, inventory, domain='map')


def require_native_evidence(c, proof):
    """Only actual normal proof supplies route references; old identities cannot."""
    validate(c)
    from .map_route_reference_variants import declared_pairs
    evidence = proof.get('named_endpoint_evidence')
    pairs = declared_pairs(c, evidence)
    if c.get('local_coverage_initialization'):
        if len(pairs) != 1: raise ValueError('Reverse initialization needs exactly one fully identified local named pair')
        pair = c['local_coverage_initialization']['initial_pair']
        if not exact_pair(pair, list(reversed(pairs[0]))):
            raise ValueError('Declared initial pair differs from complete independently identified native names')
        ref = proof.get('initial_native_reference'); spec = proof.get('initial_rendered_route_spec')
        if (not isinstance(ref, dict) or not isinstance(spec, dict) or ref.get('profile') != 'car'
                or ref.get('independent_native_read') is not True or not exact_pair(ref.get('pair'), pair)
                or not exact_pair(spec.get('pair'), pair) or ref.get('native_body_sha256') != fingerprint(ref.get('native_body'))
                or not ref.get('native_reference_receipt_sha256')):
            raise ValueError('Complete actual independent initial route request/body/rendered reference required')
        body = complete_route(ref['native_body'])
        alternatives = spec.get('alternatives')
        if (not isinstance(alternatives, list) or len(alternatives) != 1
                or alternatives[0].get('profile') != 'car' or alternatives[0].get('backend') != body
                or not alternatives[0].get('native')):
            raise ValueError('Actual native initial route body and rendered car state must agree')
    return pairs


def require_reference(c, reference):
    validate(c)
    from .map_route_reference_variants import declared_pairs
    # The whole-source proof validates named evidence separately. Every actual
    # per-mode full body/transport/request pair is still checked by core gates.
    if (reference.get('profile') not in c['allowed_modes']
            or reference.get('scope', {}).get('endpoint_request') != c['endpoint_request']):
        raise ValueError('Local named derivative reference changed original transport or exact endpoint request')
    return True


def require_reverse_operation(c, proof, *, captures=None):
    """Original saved native click/state/full-body evidence, no summary pass."""
    validate(c)
    if not c.get('local_coverage_initialization'): return True
    controls = proof.get('native_reverse_operation_controls')
    if not isinstance(controls,list) or len(controls)!=1:
        raise ValueError('Actual native reverse-button control evidence required')
    reference=controls[0]
    if (not isinstance(reference,dict) or set(reference)!={'file','sha256'}
            or not re.fullmatch(r'[0-9a-f]{64}',str(reference['sha256']))
            or 'actor' in Path(reference['file']).parts):
        raise ValueError('Immutable actual native reverse control locator required')
    try: raw=Path(reference['file']).read_bytes();record=json.loads(raw)
    except (OSError,ValueError) as error: raise ValueError('Original native reverse control bytes unavailable') from error
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('Original native reverse control bytes changed')
    bid=record.get('actual_visible_button_bid')
    if (record.get('version')!='actual-native-route-reverse-control-v1'
            or record.get('source_task_id')!=c['source_task_id']
            or record.get('native_button_selector')!='.directions_form .reverse_directions'
            or not isinstance(bid,str) or re.fullmatch(r'[0-9]+',bid) is None
            or record.get('action')!='click('+repr(bid)+')'
            or type(record.get('passive_response_count_before_action')) is not int
            or record['passive_response_count_before_action'] < 1
            or not isinstance(record.get('actual_step_observation'),dict)
            or 'last_action_error' not in record['actual_step_observation']
            or record['actual_step_observation']['last_action_error'] != ''):
        raise ValueError('Real successful native reverse-button BrowserGym action required')
    from .map_route_native_display import verified_route_checks
    initial=proof['initial_native_reference'];final=proof['references']['car']
    for role,ref in [('initial',initial),('final',final)]:
        served=record[role+'_actual_native_response']
        if not isinstance(served,dict) or served.get('complete_native_response') is not True:
            raise ValueError('Actual complete reverse native response required')
        if captures is not None and served not in captures:
            raise ValueError('Actual reverse response is absent from original complete passive capture')
        state=record['before_public_state' if role=='initial' else 'after_public_state']
        url=record['before_url' if role=='initial' else 'after_url']
        checks=verified_route_checks(ref['scope']['rendered_route_spec'],served,ref['native_body'],state,url,pinned_pair=ref['pair'])
        if not all(checks.values()): raise ValueError('Actual native reverse action state/request/body/engine disagree')
    return True
