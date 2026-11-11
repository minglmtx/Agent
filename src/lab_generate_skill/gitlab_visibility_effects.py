"""Exact native visibility propagation, not a blanket namespace/flag waiver.

Candidate capability guard. Full sixteen-table guards remain independently
required, with only these target fields factored into this comparison.
"""
FIELDS={'project_id','project_namespace_id','namespace_id','namespace_type',
        'project_visibility','namespace_visibility','lfs_enabled','emails_disabled',
        'effective_lfs_enabled','effective_emails_disabled'}

def visibility_effects_equal(before,after,spec):
    if not isinstance(before,dict) or not isinstance(after,dict) or set(before)!=FIELDS or set(after)!=FIELDS:return False
    ident=spec.get('identity');target=spec.get('value')
    if type(ident)is not int or ident<=0 or type(target)is not int or target not in (0,10,20):return False
    for row in (before,after):
        if row['project_id']!=ident or type(row['project_id'])is not int:return False
        ns=row['project_namespace_id']
        if type(ns)is not int or ns<=0 or type(row['namespace_id'])is not int or row['namespace_id']!=ns or row['namespace_type']!='Project':return False
        if type(row['project_visibility'])is not int or row['namespace_visibility']!=row['project_visibility'] or type(row['namespace_visibility'])is not int:return False
    if before['project_namespace_id']!=after['project_namespace_id'] or after['project_visibility']!=target:return False
    for name in ('lfs_enabled','emails_disabled'):
        key='effective_'+name
        if type(before[key])is not bool or type(after[key])is not bool or before[key]!=after[key]:return False
        old,new=before[name],after[name]
        if old is not None and type(old)is not bool:return False
        if new is not None and type(new)is not bool:return False
        if old is not new and not (old is None and new is before[key]):return False
    return True
