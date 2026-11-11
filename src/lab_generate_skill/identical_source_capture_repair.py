"""Close identical historical preference reservations for one capture repair.

Every old attempt still passes the complete ordinary capture-gap authority.
Aliases get exclusive historical leases, never a new actor task or copied score.
Different starts, initial values, targets, heldout aliases and live/extra attempts
remain disallowed by the same source guard and its exact-artifact checks.
"""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit

from .answer_protocol_repair import pinned, plain, regular, sha
from .bulk_source_guard import inventory_aliases
from .site_preferences_rules import require_preferences_admission

VERSION = 'identical-preference-capture-history-v1'
PROVENANCE_FIELDS = {'task_id', 'source_task_id', 'goal', 'recorded_start_paths',
                     'recorded_start_urls', 'source_trace_ids'}
CONTROL_STATE_FIELDS = ('initial_state', 'positive_state', 'wrong_state',
                        'unsaved_state', 'unsaved_ui_values', 'native_choices')


def normalize_goal(goal):
    return ' '.join(goal.lower().split()).rstrip('.')


def condition(contract):
    return {k: v for k, v in plain(contract).items() if k not in PROVENANCE_FIELDS}


def require_original_preference(contract, inventory):
    sid = contract.get('source_task_id', contract.get('task_id'))
    if (contract.get('domain') != 'reddit' or not contract.get('preferences')
            or any(contract.get(k) for k in ('query', 'membership', 'cart'))
            or contract.get('heldout_quarantine') is not False
            or contract.get('eligible_for_training') is not False
            or contract.get('task_text_changed') is not False
            or contract.get('goal_revision') or contract.get('start_revision')
            or inventory.get('task_id') != sid or inventory.get('domain') != 'reddit'
            or inventory.get('goal') != contract.get('goal')
            or inventory.get('heldout_quarantine') is not False):
        raise ValueError('Exact nonheldout original preference source required')
    urls = inventory.get('recorded_start_urls', [])
    if (not isinstance(urls, list) or not urls
            or any(not isinstance(u, str) or not u for u in urls)
            or not isinstance(inventory.get('source_trace_ids'), list)
            or not inventory['source_trace_ids']
            or any(not isinstance(t, str) or not t for t in inventory['source_trace_ids'])):
        raise ValueError('All authoritative preference starts and traces required')
    paths = [(urlsplit(u).path or '/') + ('?' + urlsplit(u).query if urlsplit(u).query else '')
             for u in urls]
    if (contract.get('start_path') != paths[0]
            or contract.get('recorded_start_paths') != paths
            or ('recorded_start_urls' in contract and contract['recorded_start_urls'] != urls)
            or ('source_trace_ids' in contract and contract['source_trace_ids'] != inventory['source_trace_ids'])):
        raise ValueError('Exact original first start and complete source provenance required')
    proof = json.loads(regular(contract['admission_result']))
    require_preferences_admission(contract, proof)
    return [{key: cycle.get(key) for key in CONTROL_STATE_FIELDS} for cycle in proof['cycles']]


def attach_identical_histories(authority, chosen, spec, spec_sha, *, terminal_query, authority_type):
    groups = spec.get('identical_source_alias_histories', [])
    authority.identical_alias_histories = []
    if not isinstance(groups, list):
        raise ValueError('Explicit identical-source history groups required')
    if not groups:
        return
    reviewed = json.loads(pinned(spec['review'])).get('identical_source_families', [])
    used = set()
    for group in groups:
        if not isinstance(group, dict) or group.get('version') != VERSION:
            raise ValueError('Reviewed identical preference history version required')
        sid = group.get('canonical_source_task_id')
        family = group.get('source_ids')
        if (not isinstance(family, list) or len(family) < 2
                or any(not isinstance(s, str) or not s for s in family)
                or family != sorted(set(family)) or sid != family[0]
                or sid not in chosen or set(chosen) & set(family) != {sid}
                or used & set(family)):
            raise ValueError('One deterministic canonical actor task per complete alias family required')
        inventory_pin = group['inventory']
        if Path(inventory_pin['path']) != authority.base / 'inventory.jsonl':
            raise ValueError('Authoritative original inventory required')
        inventory = [json.loads(line) for line in pinned(inventory_pin).decode().splitlines()]
        aliases = inventory_aliases(inventory)
        if aliases.get(sid) != set(family):
            raise ValueError('Whole authoritative original source family required')
        by = {row['task_id']: row for row in inventory}
        original = chosen[sid]
        states = require_original_preference(original, by[sid])
        normalized = normalize_goal(original['goal'])
        native_condition = condition(original)
        projection = {'version': VERSION, 'canonical_source_task_id': sid,
            'source_ids': family, 'inventory': inventory_pin,
            'condition_sha256': sha(json.dumps(native_condition, sort_keys=True, separators=(',', ':')).encode()),
            'initial_and_control_states_equal': True, 'selected_actor_tasks': 1,
            'aliases_are_not_independent_training_results': True}
        matches = [r for r in reviewed if r.get('canonical_source_task_id') == sid]
        if matches != [projection]:
            raise ValueError('Independent review must bind the identical task conditions and family')
        members = group.get('members')
        if (not isinstance(members, list) or len(members) != len(family) - 1
                or {m.get('contract', {}).get('source_task_id') for m in members} != set(family) - {sid}):
            raise ValueError('Every other original alias history is required')
        for member in members:
            contract, history = member['contract'], member['history']
            alias = contract['source_task_id']
            if (normalize_goal(contract['goal']) != normalized
                    or condition(contract) != native_condition
                    or require_original_preference(contract, by[alias]) != states
                    or history.get('source_task_id') != alias
                    or any(history.get(k) for k in ('prior_revision_reservations',
                        'completed_cpu_reservations', 'closed_cpu_option_previews'))):
                raise ValueError('Same native goal, start, account, targets and actual control states required')
            child_spec = deepcopy(spec)
            child_spec['identical_source_alias_histories'] = []
            child_spec['sources'] = [history]
            # Reuse every existing original-history check. No bypass of a saved
            # state, runtime error, live job, proof pin or foreign artifact.
            child = authority_type(authority.base, authority.wave, [contract], child_spec,
                                   spec_sha, terminal_query=terminal_query)
            if (child.original_variants or child.previous_attempts != 1
                    or len(child.artifacts) != 1 or len(child.leases) != 1
                    or authority.artifacts.keys() & child.artifacts.keys()
                    or {p for p, _ in authority.leases} & {p for p, _ in child.leases}):
                raise ValueError('One distinct closed history per identical alias required')
            authority.artifacts.update(child.artifacts)
            for path, sources in child.superseded.items():
                if sources != {alias}:
                    raise ValueError('Alias history released an unrelated reservation')
                authority.superseded.setdefault(path, set()).update(sources)
            authority.leases.extend(child.leases)
            authority.previous_attempts += 1
        used.update(family)
        authority.identical_alias_histories.append(projection)
