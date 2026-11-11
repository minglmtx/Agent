"""Contracts for a no-teacher, no-training, local skill usefulness diagnostic."""
import json
from pathlib import Path
from .admin_reset_experiment import TASK_IDS
from .generator_sft import normalize_goal


def task_rows(root,base=None):
    manifest=Path(base)/'tasks.jsonl' if base is not None and (Path(base)/'tasks.jsonl').exists() else Path(root)/'outputs/gobrowse-task-admission-plan-v1/admin_pilot_12.jsonl'
    rows=list(map(json.loads,manifest.read_text().splitlines()))
    if len({r['source_task_id'] for r in rows})!=len(rows):raise ValueError('Duplicate task manifest entries')
    return {r['source_task_id']:r for r in rows}


def admitted_tasks(root,base,phase):
    rows=task_rows(root,base);result=[]
    previous=Path(root)/'outputs/admin-improvement-v1/reset'
    if phase=='dev':
        summary=json.loads((previous/'summary.json').read_text())
        if not summary.get('reset_gate_passed'):raise ValueError('Previous reset checks failed')
        for item in summary['tasks']:
            if not item['passed']:raise ValueError('Previous controls failed')
            d=previous/item['task_id']
            result.append({'task_id':item['task_id'],'row':rows[item['task_id']],'admission':item,'initial_observation_path':str(d/'cycle-0/step-000.json'),'admission_path':str(d/'result.json')})
    elif phase=='extension':
        for task_id,row in rows.items():
            if task_id in TASK_IDS and not (Path(base)/'unified-batch.json').exists():continue
            d=Path(base)/'admission'/task_id
            item=json.loads((d/'result.json').read_text())
            if not item['passed']:continue
            result.append({'task_id':task_id,'row':row,'admission':item,'initial_observation_path':str(d/'cycle-0/step-000.json'),'admission_path':str(d/'result.json')})
    else:raise ValueError('Unknown phase')
    return result


def eligible_bank(bank,rows,*,exclude_pilot_sources=False):
    # Construction may reuse same-task experience; held-out evaluation opts out.
    if not exclude_pilot_sources:return [s for s in bank if s["domain"]=="shopping_admin"]
    ids=set(rows);goals={normalize_goal(r['goal']) for r in rows.values()}
    return [s for s in bank if s['domain']=='shopping_admin' and not ids.intersection(s['source_task_ids']) and not goals.intersection(normalize_goal(g) for g in s['source_goals'])]


def select_refs(bank,scores,k=6):
    if len(bank)!=len(scores) or len(bank)<k:raise ValueError('Invalid retrieval pool')
    return [bank[i] for i in sorted(range(len(bank)),key=lambda i:(-float(scores[i]),bank[i]['skill_id']))[:k]]


def ablation_metrics(tasks):
    # Each task has one baseline and FOUR scheduled candidates. Invalid candidates
    # are retained as failed proposal slots, not silently removed from the denominator.
    complete=[];incomplete=[]
    for t in tasks:
        slots={r['arm']:r for r in t['results']}
        if set(slots)!={'baseline','skill-0','skill-1','skill-2','skill-3'} or any(r.get('evaluation',{}).get('status')=='unknown' for r in slots.values()):
            incomplete.append(t['task_id']);continue
        baseline=slots['baseline']['evaluation']['status']=='success'
        wins=sum(slots[f'skill-{i}']['evaluation']['status']=='success' for i in range(4))
        complete.append({'task_id':t['task_id'],'baseline_success':baseline,'skill_successes':wins,'any_skill_success':wins>0})
    n=len(complete)
    return {'scored_tasks':n,'incomplete_tasks':incomplete,'baseline_success_rate':sum(x['baseline_success'] for x in complete)/n if n else None,'mean_candidate_success_rate':sum(x['skill_successes'] for x in complete)/(4*n) if n else None,'any_of_four_success_rate':sum(x['any_skill_success'] for x in complete)/n if n else None,'tasks':complete,'note':'Any-of-four uses four actor rollouts; it is not an equal-compute comparison.'}
