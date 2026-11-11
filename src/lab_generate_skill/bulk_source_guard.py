"""Authoritative source-alias guards for bulk planning and worker startup.

No actor, filesystem mutation, admission repair or model retry. Goals and traces come from
inventory; a contract cannot invent or remove its own source aliases.
"""
import hashlib
import json
from pathlib import Path
import re


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+', value) or value in ('.', '..'):
        raise ValueError('Unsafe source or actor task identifier')
    return value


def source_id(contract):
    if not isinstance(contract, dict): raise ValueError('Malformed source contract')
    return safe_id(contract.get('source_task_id', contract.get('task_id')))


def inventory_records(inventory):
    if isinstance(inventory, dict):
        result = []
        for key, row in inventory.items():
            if not isinstance(row, dict) or row.get('task_id', key) != key:
                raise ValueError('Authoritative inventory key and task identifier disagree')
            result.append(dict(row, task_id=key))
        return result
    if not isinstance(inventory, (list, tuple)): raise ValueError('Malformed authoritative inventory')
    if any(not isinstance(row, dict) for row in inventory): raise ValueError('Malformed authoritative inventory row')
    return list(inventory)


def inventory_aliases(inventory):
    """Same authoritative domain/normalized-goal/shared-trace union semantics."""
    rows = inventory_records(inventory); parent = {}; goals = {}; traces = {}
    def find(value):
        parent.setdefault(value, value)
        root = value
        while parent[root] != root: root = parent[root]
        while parent[value] != value:
            previous = parent[value]; parent[value] = root; value = previous
        return root
    def join(left, right): parent[find(left)] = find(right)
    for row in rows:
        tid = safe_id(row['task_id'])
        if tid in parent: raise ValueError('Duplicate authoritative inventory source')
        find(tid); domain = row.get('domain')
        if not isinstance(domain, str) or not domain: raise ValueError('Inventory source has no website domain')
        if not isinstance(row.get('goal', ''), str): raise ValueError('Malformed authoritative task goal')
        goal = ' '.join(row.get('goal', '').lower().split()).rstrip('.')
        if goal:
            key = domain, goal
            if key in goals: join(tid, goals[key])
            else: goals[key] = tid
        trace_ids = row.get('source_trace_ids', [])
        if not isinstance(trace_ids, (list, tuple)): raise ValueError('Malformed authoritative source traces')
        for trace in trace_ids:
            if not isinstance(trace, (str, int)) or isinstance(trace, bool): raise ValueError('Invalid authoritative source trace identity')
            key = domain, type(trace), trace
            if key in traces: join(tid, traces[key])
            else: traces[key] = tid
    groups = {}
    for tid in parent: groups.setdefault(find(tid), set()).add(tid)
    return {tid: set(groups[find(tid)]) for tid in parent}


def validate_selection(contracts, inventory, reserved=(), *, domain=None, development_only=True):
    """Reject duplicates, heldout/reserved transitive aliases before packing."""
    if type(development_only) is not bool: raise ValueError('Development scope must be explicit boolean')
    contracts = list(contracts); records = inventory_records(inventory)
    if not contracts: raise ValueError('No selected bulk tasks')
    by_id = {row['task_id']: row for row in records}; groups = inventory_aliases(records)
    expanded_reserved = set()
    for ident in reserved:
        ident = safe_id(ident); expanded_reserved.update(groups.get(ident, {ident}))
    seen, seen_bound, sources = set(), set(), []
    domains = set()
    for contract in contracts:
        tid, sid = safe_id(contract['task_id']), source_id(contract)
        original = by_id.get(sid)
        if not original or original.get('domain') != contract.get('domain') or (domain is not None and contract.get('domain') != domain):
            raise ValueError('Unknown or mixed-website authoritative source')
        aliases = groups[sid]
        if tid in seen_bound or seen & aliases: raise ValueError('Duplicate authoritative goal/trace source aliases')
        if aliases & expanded_reserved or tid in expanded_reserved: raise ValueError('Previously reserved authoritative source alias')
        if contract.get('heldout_quarantine') or any(by_id[alias].get('heldout_quarantine') for alias in aliases):
            raise ValueError('Heldout authoritative source alias')
        if development_only and contract.get('eligible_for_training'):
            raise ValueError('Bulk codebase validation scope is development only')
        seen_bound.add(tid); seen.update(aliases); sources.append(sid); domains.add(contract['domain'])
    if len(domains) != 1: raise ValueError('One website required per bulk worker')
    return {'scope': 'development' if development_only else 'explicit_training', 'domain': next(iter(domains)),
            'tasks': len(contracts), 'task_ids': [contract['task_id'] for contract in contracts], 'source_ids': sources,
            'expanded_source_ids': sorted(seen), 'aliases_by_source': {sid: sorted(groups[sid]) for sid in sources}}


def read_rows(path): return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def attempt_artifacts(directory):
    if not directory.is_dir(): return []
    return [file for file in directory.iterdir() if file.name.startswith(('generation-', 'attempt-', 'rollout', 'trajectory', 'actor-input', 'step-'))
            or file.name in ('result.json', 'attempt.json')]


def completed_current_worker(directory, task_id, current_job):
    if current_job is None: return False
    try:
        claim = json.loads((directory / 'attempt-started.json').read_text())
        result = json.loads((directory / 'result.json').read_text())
    except (OSError, ValueError, TypeError): return False
    if not isinstance(claim, dict) or not isinstance(result, dict) or not isinstance(result.get('evaluation'), dict): return False
    return (claim.get('task') == task_id and claim.get('job') == str(current_job) and claim.get('scripted') is False
            and result.get('task_id') == task_id and result.get('evaluation', {}).get('status') in ('success', 'failure')
            and result.get('status') != 'runtime_or_contract_error')


def check_startup(base, wave, manifest, *, domain=None, worker='0', current_job=None,
                  current_task_id=None, completed_task_ids=(), development_only=True):
    """Recheck actual manifests and raw attempts immediately before inference.

    Default is an untouched development worker: no past attempt is allowed.
    A caller inside the SAME active worker may explicitly list completed
    earlier tasks. They must precede current_task_id in this original manifest,
    carry a successful/failed terminal result and the exact current job claim.
    Other workers, waves, unknown/partial results and source aliases never gain
    this exception. Native proof validation remains the admitted runner's job.
    """
    base, wave, manifest = Path(base).resolve(), Path(wave).resolve(), Path(manifest).resolve()
    worker = safe_id(str(worker))
    if wave.parent != base or not manifest.is_relative_to(wave): raise ValueError('Original manifest must belong to this immediate bulk wave')
    inventory = read_rows(base / 'inventory.jsonl'); groups = inventory_aliases(inventory)
    original_path = wave / 'contracts.jsonl'
    plan_path = wave / 'bulk-plan.json'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        hashes = plan.get('manifest_hashes')
        if not isinstance(hashes, dict) or 'contracts.jsonl' not in hashes:
            raise ValueError('Original bulk plan is missing immutable manifest fingerprints')
        for name, expected in hashes.items():
            if not isinstance(name, str) or Path(name).name != name or not name.startswith('contracts') or not name.endswith('.jsonl'):
                raise ValueError('Unsafe original manifest fingerprint path')
            if not isinstance(expected, str) or hashlib.sha256((wave / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Original bulk manifest fingerprint changed')
    if (wave / 'preinference-recovery-claim').exists() or any(wave.glob('actor-recovery*')):
        raise ValueError('Original wave already has an exclusive actor recovery reservation')
    originals = read_rows(original_path)
    # Validate the complete original wave, not just one shard. Otherwise alias
    # sources split into different workers could both pass a shard-only check.
    validate_selection(originals, inventory, domain=domain, development_only=development_only)
    by_task = {row['task_id']: row for row in originals}; selected = read_rows(manifest)
    summary = validate_selection(selected, inventory, domain=domain, development_only=development_only)
    for contract in selected:
        if {key: value for key, value in contract.items() if key != 'admission_result'} != by_task.get(contract['task_id']):
            raise ValueError('Selected manifest changed the original source contract')
    selected_ids = set(summary['task_ids']); expanded = set(summary['expanded_source_ids']); actor_aliases = selected_ids | expanded
    if isinstance(completed_task_ids, (str, bytes)): raise ValueError('Completed tasks must be an explicit sequence')
    completed = {safe_id(tid) for tid in completed_task_ids}
    if current_task_id is not None:
        current_task_id = safe_id(current_task_id)
        if current_task_id not in selected_ids: raise ValueError('Current task is not in the original worker manifest')
    order = sorted(summary['task_ids'])
    if completed:
        if current_task_id not in selected_ids or current_job is None or not completed <= set(order[:order.index(current_task_id)]):
            raise ValueError('Only completed earlier tasks from this original manifest may be reused in the current worker')
    roots = [folder for folder in base.iterdir() if folder.is_dir()]
    # Two passes: a physical alias may be declared by a later manifest. A
    # collision in an earlier unrelated manifest must still be rejected.
    bindings = []
    for other in roots:
        paths = set(other.glob('contracts*.jsonl')) | set(other.glob('tasks*.jsonl'))
        paths |= set(other.glob('actor-recovery*/contracts*.jsonl'))
        for path in paths:
            for binding in read_rows(path):
                sid, tid = source_id(binding), safe_id(binding['task_id'])
                bindings.append((other, path, sid, tid))
                if sid in expanded: actor_aliases.add(tid)
    bound_sources = {}
    for other, path, sid, tid in bindings:
        if sid not in expanded and tid not in actor_aliases: continue
        if other != wave or path.parent != wave:
            raise ValueError('Another wave or recovery reserves an authoritative source alias')
        previous = bound_sources.get(tid)
        if sid not in expanded or (previous is not None and sid not in groups[previous]):
            raise ValueError('Same physical actor task identifier maps to a different source')
        bound_sources[tid] = sid
    allowed_out = wave / 'actor' / worker
    for other in roots:
        for actor in other.glob('actor*'):
            if not actor.is_dir(): continue
            candidates = {actor / alias for alias in actor_aliases}
            for child in actor.iterdir():
                if child.is_dir(): candidates.update(child / alias for alias in actor_aliases)
            for directory in candidates:
                markers = attempt_artifacts(directory)
                if not markers: continue
                tid = directory.name
                allowed = (directory == allowed_out / tid and tid in completed
                           and completed_current_worker(directory, tid, current_job))
                if not allowed: raise ValueError('Original-source alias has another generation, claim, partial or terminal actor attempt')
    return {**summary, 'original_wave_sources_validated': len(originals), 'current_worker': worker,
            'completed_earlier_task_ids': sorted(completed), 'actual_raw_attempts_checked': True,
            'api_calls': 0, 'actor_attempts_started': 0, 'files_modified': False}
