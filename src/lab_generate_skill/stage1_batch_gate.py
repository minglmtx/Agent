"""Training-scope and two-cold initial-state gates for local pilot batches."""
import csv
import io
from pathlib import Path

from .generator_sft import file_hash
from .stage1_local import read_pinned_json


def require_derived_runtime(plan, source, cap, formal):
    """Accept only explicitly recorded initial-surface changes in a trial capsule."""
    proof = read_pinned_json(plan['runtime_derivation'])
    if (proof.get('passed') is not True or proof.get('candidate_capsule') != plan['capsule']
            or proof.get('formal_capsule') != plan['formal_capsule']
            or proof.get('source_task_id') != source['source_task_id']
            or proof.get('initial_qualification') != source['initial_qualification']
            or proof.get('guarded_live_trial_authorized') is not True
            or proof.get('production_runtime_modified') is not False):
        raise ValueError('Candidate runtime derivation is not bound to this source and initial proof')
    base = read_pinned_json(proof['base_capsule'])
    if any(base['members'].get(n) != ref for n, ref in formal['members'].items()):
        raise ValueError('Candidate base does not retain the registered formal runtime')
    execution_updates = require_execution_updates(plan, source, proof, cap) if proof.get('execution_review') else {}
    changed = {r['name']: r for r in proof['patches']}
    if len(changed) != len(proof['patches']):
        raise ValueError('Duplicate runtime patch')
    for name, old in base['members'].items():
        actual = cap['members'].get(name)
        if name in changed:
            patch = changed[name]
            if (old['sha256'] != patch['before_sha256'] or actual is None
                    or actual['sha256'] != patch['after_sha256']):
                raise ValueError('Candidate changed bytes disagree with qualified patch')
        elif name in execution_updates:
            update = execution_updates[name]
            if old != update['before'] or actual != update['after']:
                raise ValueError('Execution update differs from the retained initial base')
        elif actual != old:
            raise ValueError('An undeclared runtime file changed')
    additions = proof['added_members']
    if {k:v for k,v in cap['members'].items() if k not in base['members']} != additions:
        raise ValueError('Candidate added code differs from the reviewed runtime')
    qualified = read_pinned_json(source['initial_qualification'])
    if proof['patches'] != qualified.get('patches', []):
        raise ValueError('Candidate is not the exact qualified stable-surface implementation')
    return proof



def require_execution_updates(plan, source, proof, cap):
    """Retain original cold evidence across an explicitly reviewed execution delta.

    This does not turn a changed surface into an old capture. The separate CPU
    review must bind the unchanged source, parent derivation, all changed bytes,
    ten actual saved contexts. The build report separately verifies the new
    entry's pre-inference boundary before any outer source admission.
    """
    review = read_pinned_json(proof['execution_review'])
    parent = read_pinned_json(review['parent_plan'])
    original = read_pinned_json(parent['runtime_derivation'])
    qref = source['initial_qualification']; qualified = read_pinned_json(qref)
    if (review.get('version') != 'retained-initial-execution-delta-review-v1'
            or review.get('passed') is not True
            or review.get('candidate_capsule') != plan['capsule']
            or review.get('parent_capsule') != parent['capsule']
            or parent['sources'] != [source]
            or review.get('source_task_id') != source['source_task_id']
            or review.get('initial_qualification') != qref
            or review.get('actual_captured_contexts') != qualified['actual_captured_contexts']
            or review.get('complete_context_bindings_verified') != 10
            or review.get('initial_public_functions_unchanged') is not True
            or review.get('source_initial_pipeline_unchanged') is not True
            or review.get('initial_modules_remaining_ast_checked') is not True
            or review.get('new_actor_calls') != 0 or review.get('new_generation_model_calls') != 0
            or review.get('new_cold_captures') != 0):
        raise ValueError('Execution delta lacks retained source/initial evidence')
    for key in ('base_capsule', 'formal_capsule', 'initial_qualification', 'patches'):
        if proof[key] != original[key]:
            raise ValueError('Execution update changed the original initial qualification')
    parent_cap = read_pinned_json(parent['capsule'])
    require_derived_runtime(parent, source, parent_cap, read_pinned_json(parent['formal_capsule']))
    old = parent_cap['members']
    actual = {n: dict(before=old.get(n), after=cap['members'].get(n))
              for n in set(old) | set(cap['members']) if old.get(n) != cap['members'].get(n)}
    if (actual != review.get('member_delta') or not actual
            or any(row['after'] is None for row in actual.values())
            or proof.get('execution_updates') != actual):
        raise ValueError('Execution delta contains undeclared or removed members')
    initial_files = review.get('unchanged_initial_members', {})
    required_initial = {
        'scripts/run_site_navigation_skill_once.py', 'scripts/local_pilot_episodes.py',
        'src/lab_generate_skill/stage1_context_capture.py',
        'src/lab_generate_skill/stage1_initial_binding.py', 'src/lab_generate_skill/stage1_live_binding.py',
        'src/lab_generate_skill/actor_protocol.py', 'src/lab_generate_skill/observation_budget.py',
        'src/lab_generate_skill/action_history.py', 'src/lab_generate_skill/ax_observation.py',
    }
    if (set(initial_files) != required_initial or any(old.get(n) != ref or cap['members'].get(n) != ref
                                 for n, ref in initial_files.items())):
        raise ValueError('Initial capture dependency bytes changed')
    # The review is an actual frozen CPU artifact, not a replacement cold report.
    # Its file/AST checks are independently reviewable; root source admission and
    # the actual live initial request guard remain required by the outer caller.
    return {n: row for n, row in actual.items() if row['before'] is not None}


def require_source(plan, source, *, live):
    if (plan.get('purpose') != 'engineering_pilot' or plan.get('training_data') is not False
            or plan.get('paid_api_calls') != 0 or plan.get('automatic_retry') is not False):
        raise ValueError('Only an explicit no-paid-API engineering pilot is supported')
    if plan.get('workflow') != dict(retrieved_skills=6, candidate_skills=4,
            mandatory_teacher_first_round=True, maximum_teacher_rounds=3,
            frozen_actor='Qwen2.5-7B-Instruct', local_generator_and_teacher='Qwen3-8B'):
        raise ValueError('Batch policy changed')
    parallel = plan.get('parallelism', {})
    if (type(parallel.get('max_concurrent_sources')) is not int
            or not 1 <= parallel['max_concurrent_sources'] <= 2
            or parallel.get('actor_attempts_per_source') != 1
            or parallel.get('isolated_source_workspaces') is not True):
        raise ValueError('Independent sources require bounded, isolated execution')
    ids = [s['source_task_id'] for s in plan['sources']]
    if len(set(ids)) != len(ids) or source not in plan['sources']:
        raise ValueError('Sources must be unique members of this batch')
    pointer = read_pinned_json(plan['training_pointer'])
    table = Path(pointer['tasks'])
    if file_hash(table) != pointer['tasks_sha256']:
        raise ValueError('Training registration changed')
    rows = list(csv.DictReader(io.StringIO(table.read_text(encoding='utf-8-sig'))))
    matches = [r for r in rows if r['source_task_id'] == source['source_task_id']]
    if len(matches) != 1:
        raise ValueError('Source must occur exactly once in the training register')
    row = matches[0]
    allowed = read_pinned_json(plan['allowed'])
    if (row['split'] != 'train' or row['status'] not in ('success', 'failure')
            or any(row[k] != source[k] for k in ('active_task_id', 'runtime_task_id', 'domain'))
            or allowed[source['active_task_id']] != dict(domain=row['domain'], task_instruction=row['current_goal'])):
        raise ValueError('Source identity, training split or literal goal changed')
    for key in ('native_contract', 'admission'):
        read_pinned_json(source[key])
    cap, base = read_pinned_json(plan['capsule']), read_pinned_json(plan['formal_capsule'])
    derivation = None
    if plan.get('runtime_derivation'):
        derivation = require_derived_runtime(plan, source, cap, base)
    elif any(cap['members'].get(name) != ref for name, ref in base['members'].items()):
        raise ValueError('Pilot capsule must retain the registered formal runtime')
    if live:
        qualification = read_pinned_json(source['initial_qualification'])
        if qualification.get('version') == 'two-cold-initial-capture-qualification-v1':
            if (qualification.get('passed') is not True or qualification.get('source') != {
                    k:v for k,v in source.items() if k not in ('initial_qualification', 'checkpoint', 'checkpoint_mode')}
                    or qualification.get('cold_instances') != 2
                    or qualification.get('resets_per_cold') != [5, 5]
                    or qualification.get('exact_ax_equal') is not True
                    or qualification.get('protected_state_checks') != 10
                    or len(qualification.get('actual_captured_contexts', [])) != 10
                    or derivation is None
                    or qualification.get('capsule') != derivation['base_capsule']):
                raise ValueError('Stable-surface source lacks exact two-cold evidence and derived runtime')
            read_pinned_json(qualification['actual_captured_contexts'][0])
            if file_hash(qualification['initial_observation']['path']) != qualification['initial_observation']['sha256']:
                raise ValueError('Qualified initial observation changed')
            return dict(passed=True, source_task_id=source['source_task_id'], live=True,
                        guarded_live_trial=True, ordinary_actor_already_qualified=False,
                        training_data=False, formal_training_targets=0, paid_api_calls=0)
        expected = {k: source[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                                          'domain', 'native_contract', 'admission')}
        expected['capsule'] = plan['capsule']
        if (qualification.get('passed') is not True or qualification.get('binding') != expected
                or qualification.get('cold_instances', 0) < 2
                or qualification.get('resets_per_cold', 0) < 5
                or qualification.get('exact_initial_observation') is not True
                or qualification.get('protected_state_checks_passed') is not True
                or qualification.get('actor_runtime_compatible') is not True):
            raise ValueError('Live source lacks two-cold, runtime-compatible initial qualification')
        # This first generic version deliberately admits only unmodified Actor
        # runtime bytes. A future stabilization capsule needs its own review.
        if qualification.get('runtime_patches', []) or qualification.get('observation_policy') != 'identity':
            raise ValueError('A modified Actor surface needs a separately qualified runtime')
        read_pinned_json(qualification['actual_captured_contexts'][0])
        if file_hash(qualification['initial_observation']['path']) != qualification['initial_observation']['sha256']:
            raise ValueError('Qualified initial observation changed')
    return dict(passed=True, source_task_id=source['source_task_id'], live=live,
                training_data=False, formal_training_targets=0, paid_api_calls=0)
