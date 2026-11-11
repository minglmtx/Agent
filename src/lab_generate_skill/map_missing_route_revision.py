"""Explicit route parameters for tasks whose original start has no route.

This creates a training derivative, never recovers intent from later actor
actions. Native named-place identities, full route controls and normal actor
execution remain separate requirements before admission.
"""
from copy import deepcopy
from .map_route_normal_capture import fingerprint
from .source_revision_binding import binding, local_path, require_source_binding
from .map_native_identity_declarations import POLICIES

VERSION = 'explicit-missing-route-training-v1'
SUFFIX = '--explicit-route-training-v1'


def _construct(original, inventory, queries, mode):
    if (original.get('endpoint_request', {}).get('kind') != 'missing_initial_route'
            or original.get('completion_kind') != 'longest_turn_segments'
            or original.get('goal_revision') or original.get('training_initialization')
            or inventory.get('task_id') != original.get('source_task_id')
            or inventory.get('domain') != 'map' or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != original.get('goal')
            or inventory.get('source_trace_ids') != original.get('source_trace_ids')):
        raise ValueError('Bound non-heldout original longest-segment task with missing route required')
    if (not isinstance(queries, list) or len(queries) != 2 or queries[0] == queries[1]
            or any(not isinstance(q, str) or q not in POLICIES for q in queries)
            or mode not in original.get('allowed_modes', []) or mode not in ('car', 'bike', 'foot')):
        raise ValueError('Two declared named endpoints and one originally allowed mode required')
    urls = inventory.get('recorded_start_urls')
    if not isinstance(urls, list) or not urls:
        raise ValueError('All original recorded starts required')
    paths = [local_path(u) for u in urls]
    goal = ('Get ' + {'car': 'driving', 'bike': 'cycling', 'foot': 'walking'}[mode]
            + ' directions from ' + queries[0] + ' to ' + queries[1]
            + '. Identify all numbered segments tied for the largest distance displayed '
              'in the turn-by-turn list. Compare displayed metres and kilometres in common units.')
    c = deepcopy(original)
    from .map_native_route_runtime import MARKER
    c.update(task_id=original['source_task_id'] + SUFFIX, domain='map',
             original_goal=original['goal'], goal=goal, task_text_changed=True,
             recorded_start_urls=deepcopy(urls), recorded_start_paths=paths,
             start_path=paths[0], start_revision=None, heldout_quarantine=False,
             allowed_modes=[mode], endpoint_request={'kind': 'named_places', 'queries': deepcopy(queries)},
             map_native_route=deepcopy(MARKER), completion={},
             normal_admitted=False, eligible_for_training=False,
             is_explicit_derivative=True, original_evaluation_equivalence=False)
    c['goal_revision'] = dict(version=VERSION, original_goal=original['goal'], derived_goal=goal,
        reason='The recorded initial state has no route. Endpoints and mode are explicitly supplied training parameters, not inferred original intent.',
        equivalent_to_original_goal=False, original_contract=deepcopy(original),
        original_contract_sha256=fingerprint(original), derived_queries=deepcopy(queries),
        derived_mode=mode, later_actor_actions_used_as_initial_state=False)
    return c


def derive(original, inventory, queries, mode='car'):
    c = _construct(original, inventory, queries, mode)
    validate(c)
    return c


def validate(c):
    binding(c)
    revision = c.get('goal_revision', {})
    original = revision.get('original_contract')
    if (revision.get('version') != VERSION or not isinstance(original, dict)
            or revision.get('original_contract_sha256') != fingerprint(original)):
        raise ValueError('Complete immutable missing-route original required')
    inventory = dict(task_id=c['source_task_id'], domain=c['domain'], goal=c['original_goal'],
        heldout_quarantine=c['heldout_quarantine'], source_trace_ids=c['source_trace_ids'],
        recorded_start_urls=c['recorded_start_urls'])
    expected = _construct(original, inventory, revision.get('derived_queries'), revision.get('derived_mode'))
    if {k: v for k, v in c.items() if k != 'admission_result'} != expected:
        raise ValueError('Undeclared missing-route goal, start, source, mode or predicate change')
    return binding(c)


def require_original_binding(c, controlled, inventory):
    validate(c)
    return require_source_binding(c, controlled, inventory, domain='map')


def require_native_evidence(c, proof):
    validate(c)
    from .map_route_reference_variants import declared_pairs
    # Parameters are public, but geographic object identities cannot be guessed.
    return declared_pairs(c, proof.get('named_endpoint_evidence'))


def require_reference(c, reference):
    validate(c)
    if (reference.get('profile') not in c['allowed_modes']
            or reference.get('scope', {}).get('endpoint_request') != c['endpoint_request']):
        raise ValueError('Independent route must match exactly declared endpoints and mode')
    return True
