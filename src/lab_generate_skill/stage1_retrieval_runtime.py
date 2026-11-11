"""Narrow CPU builder for ready-enabled derivatives of qualified pilot entries.

This is build-time code. It never changes an Actor, evaluator, qualification,
checkpoint, source identity, or the frozen production capsule. The caller must
execute the original source-specific gate and runtime attestation after build.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

READY_MEMBER = 'src/lab_generate_skill/stage1_retrieval_ready.py'
SUPPORTED_ENTRIES = {
    'scripts/run_local_pilot_batch_source.py',
    'scripts/run_local_pilot_admin_batch_source.py',
    'scripts/run_local_pilot_next2_source.py',
    'scripts/run_local_pilot_group6_source.py',
}


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(ref):
    if sha(ref['path']) != ref['sha256']:
        raise ValueError('Changed retrieval-runtime input: ' + ref['path'])
    return json.loads(Path(ref['path']).read_text())


def pin(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return pin(path)


def upgrade_entry(original):
    """Apply only the reviewed retrieval edits; retain all site adapters."""
    text = original
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Retrieval insertion is absent, ambiguous, or already applied')
        text = text.replace(old, new)

    marker = '    baseline = fingerprint(dict(\n'
    replace(marker,
        '    # Ready inputs are optional for fresh sources. Checkpoints retain the exact\n'
        '    # original references and never read a ready artifact, including an invalid\n'
        '    # one. A supplied fresh-source artifact fails closed before model/site work.\n'
        '    ready_refs = None\n'
        "    if not source.get('checkpoint') and 'retrieval_ready' in plan:\n"
        '        from lab_generate_skill.stage1_retrieval_ready import consume_ready\n'
        '        ready_refs = consume_ready(plan, source, goal=goal, eligible=eligible, scope=scope)\n'
        + marker)
    old_entries = ('    entries = ENTRIES if replay_only else LIVE_ENTRIES\n'
                   if '    entries = ENTRIES if replay_only else LIVE_ENTRIES\n' in text
                   else '    entries = LIVE_ENTRIES\n')
    new_entries = ('    entries = list(LIVE_ENTRIES if ready_runtime else (ENTRIES if replay_only else LIVE_ENTRIES))\n'
                   if 'if replay_only' in old_entries else '    entries = list(LIVE_ENTRIES)\n')
    replace(old_entries,
        '    # Executed entry identities belong to the capsule, not to whether this\n'
        '    # invocation retrieves or resumes. Retained receipts require the same list.\n'
        "    ready_runtime = ('src/lab_generate_skill/stage1_retrieval_ready.py' in\n"
        "                     read_pinned_json(plan['capsule'])['members'])\n"
        '    if ready_refs is not None and not ready_runtime:\n'
        "        raise ValueError('Ready-enabled entry must freeze the CPU retrieval helper')\n" + new_entries +
        '    if ready_runtime:\n'
        "        entries.append('src/lab_generate_skill/stage1_retrieval_ready.py')\n")
    replace('        encoder = vectors = None\n    else:\n',
        '        encoder = vectors = None\n'
        '    elif ready_refs is not None:\n'
        '        refs = ready_refs\n'
        '        require_runtime_references(refs, bank=eligible)\n'
        '        encoder = vectors = None\n    else:\n')
    replace('        if not prior:\n            query = encoder.encode(',
            '        if not prior and ready_refs is None:\n            query = encoder.encode(')
    replace("            reused_checkpoint=source.get('checkpoint')))\n",
        "            reused_checkpoint=source.get('checkpoint'),\n"
        "            retrieval_ready=(plan['retrieval_ready'][sid] if ready_refs is not None else None)))\n")
    # Compile only inside the CPU build allocation; no code executes here.
    compile(text, '<ready-enabled-pilot-entry>', 'exec')
    return text


def require_delta(parent_plan, parent_cap, candidate_cap, *, entry, ready_ref,
                  old_entry_text, new_entry_text):
    """Only the named orchestration entry and one additive CPU helper may differ."""
    if entry not in SUPPORTED_ENTRIES:
        raise ValueError('Unsupported pilot entry')
    if len(parent_plan.get('sources', [])) != 1 or parent_plan['sources'][0].get('checkpoint'):
        raise ValueError('Only one fresh source may receive a new runtime; checkpoint runtime is immutable')
    if not parent_plan.get('runtime_derivation'):
        raise ValueError('This builder requires an existing reviewed derived-runtime qualification')
    if READY_MEMBER in parent_cap['members'] or entry not in parent_cap['members']:
        raise ValueError('Parent runtime is not the original unextended entry')
    if upgrade_entry(old_entry_text) != new_entry_text:
        raise ValueError('Entry changes exceed the reviewed retrieval-only transformation')
    if set(candidate_cap['members']) != set(parent_cap['members']) | {READY_MEMBER}:
        raise ValueError('Candidate runtime added or removed unrelated members')
    expected_entry = dict(bytes=len(new_entry_text.encode()),
                          sha256=hashlib.sha256(new_entry_text.encode()).hexdigest())
    expected_ready = dict(bytes=Path(ready_ref['path']).stat().st_size, sha256=ready_ref['sha256'])
    if sha(ready_ref['path']) != ready_ref['sha256']:
        raise ValueError('Reviewed CPU helper changed')
    for name, old in parent_cap['members'].items():
        if candidate_cap['members'][name] != (expected_entry if name == entry else old):
            raise ValueError('Candidate changed a protected original member: ' + name)
    if candidate_cap['members'][READY_MEMBER] != expected_ready:
        raise ValueError('Candidate CPU helper differs from verified retrieval implementation')
    return dict(changed_existing_members=[entry], added_members=[READY_MEMBER],
                preserved_parent_members=len(parent_cap['members'])-1,
                actor_evaluator_observation_guard_and_checkpoint_bytes_unchanged=True)


def extend_derivation(parent_plan, candidate_ref, candidate_cap):
    """Re-declare additions against the original qualified base, retaining patches."""
    old = read(parent_plan['runtime_derivation'])
    source = parent_plan['sources'][0]
    if (old.get('passed') is not True or old.get('candidate_capsule') != parent_plan['capsule']
            or old.get('initial_qualification') != source['initial_qualification']
            or old.get('source_task_id') != source['source_task_id']):
        raise ValueError('Parent derivation does not bind the selected qualified source')
    base = read(old['base_capsule'])
    qualified = read(source['initial_qualification'])
    if old['patches'] != qualified.get('patches', []):
        raise ValueError('Original surface patches differ from original qualification')
    result = deepcopy(old)
    result['candidate_capsule'] = candidate_ref
    result['added_members'] = {name: value for name, value in candidate_cap['members'].items()
                               if name not in base['members']}
    result['retrieval_ready_extension'] = dict(parent_capsule=parent_plan['capsule'],
        parent_derivation=parent_plan['runtime_derivation'],
        initial_qualification_reused_without_changes=source['initial_qualification'],
        original_surface_patches_unchanged=True, production_runtime_modified=False,
        new_actor_calls=0, new_model_calls=0)
    return result
