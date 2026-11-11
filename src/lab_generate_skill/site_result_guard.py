"""Keep infrastructure uncertainty separate from a directly established goal failure."""
from copy import deepcopy


def guard_site_result(judgment, *, runtime_error, selected_records_unchanged):
    result=deepcopy(judgment)
    if runtime_error:
        return {'status':'unknown','reward':None,'checks':{},'reason':'Runtime error prevents reliable terminal evaluation'}
    if selected_records_unchanged:return result
    # A wrong valid terminal object remains a failed goal even if the actor also
    # changed unrelated state. Do not discard that independent evidence.
    if result.get('status')=='failure':
        result['selected_records_unchanged']=False
        result['state_change_requires_review']=True
        result['reason']='Terminal goal conditions failed; protected records also changed and require attribution review'
        return result
    # A nominal success with unexpected side effects needs a review; do not
    # silently accept it, or pretend we know whether the change was intentional.
    return {'status':'unknown','reward':None,'checks':result.get('checks',{}),
            'reason':'Protected records changed; nominal completion requires state review',
            'selected_records_unchanged':False,'state_change_requires_review':True}
