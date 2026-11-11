"""Protect unrelated observed state during a declared single product edit.

A native save may materialize an inherited default. Only exact, reviewed
before/after transitions on the same product can be declared by the trusted
specification. This grants neither arbitrary writes nor a success by itself.
"""
from copy import deepcopy

def one(rows, pid):
    matches=[r for r in rows if str(r['entity_id'])==str(pid)]
    if len(matches)!=1:raise ValueError('Unique product state required')
    return matches[0]

def protected_update_checks(binding, before, after):
    spec=binding['spec'];pid=binding['product_id'];name=spec['product'];field=spec['field'];scope=str(binding['scope_id'])
    if spec.get('kind')!='update' or spec.get('protect_unrelated_state') is not True:
        raise ValueError('Explicit single-product update protection required')
    original=one(before['products'][name],pid)
    current=one(after['products'][name],pid)
    if current['sku']!=original['sku'] or current['name']!=original['name']:
        return {'target_product_identity_unchanged':False,'unrelated_task_state_unchanged':False}
    restored=deepcopy(after);target=one(restored['products'][name],pid)
    oldvalues=original['attributes'].get(field,{})
    newvalues=target['attributes'].get(field,{})
    if not isinstance(oldvalues,dict) or not isinstance(newvalues,dict):raise ValueError('Scoped attribute evidence required')
    # Restore only the permitted field/scope. Other fields/scopes stay intact
    # for the full observed-state comparison below.
    if scope in oldvalues:newvalues[scope]=oldvalues[scope]
    else:newvalues.pop(scope,None)
    if newvalues or field in original['attributes']:target['attributes'][field]=newvalues
    else:target['attributes'].pop(field,None)
    original_record=one(before['records']['product'],pid)
    final_record=one(restored['records']['product'],pid)
    seen=set()
    for change in spec.get('native_save_normalizations',[]):
        key=change['field']
        if key in seen or key in ('entity_id','sku','name',field):raise ValueError('Distinct nonidentity normalization required')
        seen.add(key)
        present=change.get('before_present',True)
        if type(present) is not bool:raise ValueError('Explicit normalization presence required')
        if (key in original_record)==present and original_record.get(key)==change['before'] and final_record.get(key)==change['after'] and key in final_record:
            if present:final_record[key]=original_record[key]
            else:final_record.pop(key)
    return {'target_product_identity_unchanged':True,'unrelated_task_state_unchanged':restored==before}
