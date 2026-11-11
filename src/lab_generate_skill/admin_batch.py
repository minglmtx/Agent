"""Full-admin inventory and strict all-failed triage, without model calls."""
EXPECTED_ARMS = {'baseline', 'skill-0', 'skill-1', 'skill-2', 'skill-3'}


def classify_attempts(results):
    names = [r.get('arm') for r in results]
    if len(names) != len(set(names)):
        return 'invalid_records'
    if set(names) != EXPECTED_ARMS:
        return 'incomplete'
    if any(r.get('evaluation', {}).get('status') not in ('success', 'failure') or r.get('error') for r in results):
        return 'runtime_or_evaluation_issue'
    if any(r.get('actor_attempts') != 1 or
           r.get('finish_reason') == 'invalid_generator_candidate' or
           r.get('evaluation', {}).get('reason') == 'invalid_generator_candidate' for r in results):
        return 'candidate_or_execution_issue'
    if all(r['evaluation']['status'] == 'failure' for r in results):
        return 'all_failed'
    return 'has_success'


def triage_tasks(tasks):
    buckets = {name: [] for name in ('all_failed','has_success','incomplete',
               'runtime_or_evaluation_issue','candidate_or_execution_issue','invalid_records')}
    seen = set()
    for task in tasks:
        if task['task_id'] in seen:raise ValueError('Duplicate task in batch triage')
        seen.add(task['task_id'])
        results=task.get('results',[])
        category=classify_attempts(results)
        buckets[category].append({'task_id':task['task_id'],'goal':task.get('goal'),
                                 'recorded_conditions':len(results),
                                 'successful_conditions':[r['arm'] for r in results if r.get('evaluation',{}).get('status')=='success']})
    return {'counts':{k:len(v) for k,v in buckets.items()},'tasks':buckets,
            'all_failed_definition':'Exactly five scored actor executions: one baseline and four valid candidates, each executed once, all failing. Missing execution, invalid candidates and unknown rewards are separate.',
            'diagnosis':'All-failed is a review queue, not an attribution to the actor.'}
