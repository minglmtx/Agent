"""Bind Map preparation to authoritative sources without changing execution.

Trajectory order is not task-inventory order. This compiler is for unadmitted
candidates only; it cannot migrate existing control proofs or actor results.
"""
from copy import deepcopy

from .source_revision_binding import binding, fingerprint, local_path, require_source_binding


def bind_candidate(candidate, inventory, source):
    binding(candidate)
    if (candidate.get('domain') != 'map' or candidate.get('split') != 'train'
            or candidate.get('native_controls_passed') is not False
            or candidate.get('training_admitted') is not False
            or candidate.get('actor_submitted') is not False
            or candidate.get('admission_result') or candidate.get('actor_attempts', 0)
            or source.get('domain') != 'map' or source.get('split') != 'train'
            or source.get('heldout_id_goal_trace_overlap') is not False
            or source.get('start_verified_from_original_observation') is not True
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('domain') != 'map'
            or inventory.get('task_id') != candidate['source_task_id']
            or source.get('source_task_id') != candidate['source_task_id']
            or inventory.get('goal') != candidate['original_goal']
            or source.get('original_goal') != candidate['original_goal']):
        raise ValueError('Unadmitted training candidate and matching authoritative source required')
    traces = source.get('source_traces', [])
    ids = [t['trace_id'] for t in traces]
    urls = [t['initial_document_url'] for t in traces]
    authoritative_urls = inventory.get('recorded_start_urls', [])
    authoritative_ids = inventory.get('source_trace_ids', [])
    if (not traces or len(ids) != len(set(ids))
            or len(authoritative_ids) != len(set(authoritative_ids))
            or len(candidate['source_trace_ids']) != len(set(candidate['source_trace_ids']))
            or set(ids) != set(authoritative_ids) or set(ids) != set(candidate['source_trace_ids'])
            or set(urls) != set(authoritative_urls) or set(urls) != set(candidate['recorded_start_urls'])
            or [local_path(u) for u in urls] != [t['initial_path'] for t in traces]):
        raise ValueError('All original trace identities and observed start URLs must match')
    result = deepcopy(candidate)
    result['recorded_start_urls'] = list(authoritative_urls)
    result['recorded_start_paths'] = list(map(local_path, authoritative_urls))
    result['source_trace_ids'] = list(authoritative_ids)
    first = result['recorded_start_paths'][0]
    if result['start_path'] == first:
        result['start_revision'] = None
    elif not result.get('start_revision') or result['start_revision']['original_start'] != first:
        result['start_revision'] = dict(
            version='authoritative-map-initial-context-v1', original_start=first,
            derived_start=result['start_path'], equivalent_to_original=False,
            reason='Keep the explicitly selected candidate start unchanged; declare its difference '
                   'from the authoritative original start. This is a training derivative, not '
                   'evidence that the original starting state was tested.')
    result.pop('candidate_fingerprint', None)
    require_source_binding(result, result, inventory, domain='map')
    result['candidate_fingerprint'] = fingerprint(result)
    return result
