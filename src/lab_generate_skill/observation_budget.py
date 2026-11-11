"""Explicit AX-only prompt budgeting; task, skill, errors and history are immutable."""
import copy
import json

class ObservationBudgetError(ValueError):
    pass


def fit_actor_messages(messages, count_tokens, maximum):
    original=count_tokens(messages)
    if original<=maximum:return messages, {'input_tokens':original,'original_tokens':original,'truncated':False}
    result=copy.deepcopy(messages)
    body=json.loads(result[-1]['content'])
    tree=body.get('observation')
    if not isinstance(tree,str):raise ObservationBudgetError('Missing structured AX observation for budgeting')
    lines=tree.splitlines()
    def candidate(n):
        payload={**body,'observation':'\n'.join(lines[:n])+('\n[AX shortened at a complete line; scroll or use page filters to inspect more.]' if n<len(lines) else ''),
            'observation_budget':{'truncated':n<len(lines),'original_lines':len(lines),'retained_lines':n}}
        result[-1]['content']=json.dumps(payload,ensure_ascii=False)
        return count_tokens(result)
    if candidate(0)>maximum:raise ObservationBudgetError('Task, skill and history alone exceed the context budget')
    low,high=0,len(lines)
    while low<high:
        mid=(low+high+1)//2
        if candidate(mid)<=maximum:low=mid
        else:high=mid-1
    tokens=candidate(low)
    if low==0:raise ObservationBudgetError('No observation line fits alongside task, skill and history')
    return result,{'input_tokens':tokens,'original_tokens':original,'truncated':low<len(lines),'original_lines':len(lines),'retained_lines':low}
