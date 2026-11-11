"""Qualify one printing-interface repair from a closed, unchanged task attempt."""
from .actor_capability_preflight import require_capabilities


def require_conflict(contract,index,values,review):
    sid=contract.get('source_task_id');tid=contract['task_id']
    result=values['result.json'];trace=values['trajectory.json']
    matching=[r for r in review.get('sources',[])if r.get('source_task_id')==sid and r.get('task_id')==tid]
    if (contract.get('browser_capabilities',{}).get('print_to_pdf')is not True
            or result.get('task_id')!=tid or result.get('actor_attempts')!=1
            or result.get('error')is not None or result.get('evaluation',{}).get('status')!='failure'
            or trace.get('task_instruction')!=contract['goal']or len(matching)!=1):
        raise ValueError('Exact unchanged failed print attempt required')
    row=matching[0]
    if (row.get('valid_result')is not False or row.get('attribution')!='codebase'
            or row.get('archive',{}).get('sha256')!=index['archive_sha256']
            or row.get('archive',{}).get('members')!=len(index['members'])
            or row.get('independent_judgment')!=result['evaluation']):
        raise ValueError('Independent capability-conflict review required')
    initial=values.get('step-000.json',{}).get('observation',{})
    generations=[v for k,v in values.items()if k.startswith('generation-')]
    if initial.get('browser_capabilities',{}).get('print_to_pdf')is not True or not generations:
        raise ValueError('Browser printing was not available in the original episode')
    for generation in generations:
        messages=generation.get('messages',[])
        systems=[m['content']for m in messages if m.get('role')=='system']
        if not systems or any('print_page'in s for s in systems):
            raise ValueError('Actual old prompt does not demonstrate missing print operation')
    # The retry must execute under a corrected protocol; retaining the old
    # public operation list cannot qualify even with a diagnostic report.
    require_capabilities(contract)
