"""Candidate persisted-node completion checks for explicit local Map derivatives.

No task is admitted by this module. Callers must bind public parameters, initial
state, account, allowed writes and reset evidence independently. Never infer a
saved edit from the browser's form or the actor's completion message.
"""
from decimal import Decimal, InvalidOperation
import math

VERSION = 'native-persisted-map-node-v1'


def validate_spec(spec):
    required={'operation','tags','latitude','longitude','tolerance_metres'}
    if not isinstance(spec,dict) or not required<=set(spec) or spec['operation']not in ('create','update'):
        raise ValueError('Explicit create/update parameters required')
    if set(spec)!=required|({'node_id'}if spec['operation']=='update'else set()):
        raise ValueError('Unknown or incomplete node completion parameters')
    tags=spec['tags']
    if not isinstance(tags,dict) or not tags or any(not isinstance(k,str)or not k or not isinstance(v,str)or not v for k,v in tags.items()):
        raise ValueError('Nonempty exact requested tags required')
    for k,bound in [('latitude',90),('longitude',180)]:
        if isinstance(spec[k],bool):raise ValueError('Numeric coordinates required')
        try:value=Decimal(str(spec[k]))
        except InvalidOperation as e:raise ValueError('Numeric coordinates required')from e
        if not value.is_finite() or abs(value)>bound:raise ValueError('Invalid coordinate')
    tolerance=spec['tolerance_metres']
    if type(tolerance)not in (int,float)or not math.isfinite(tolerance)or not 0<tolerance<=100:
        raise ValueError('Explicit bounded placement tolerance required')
    if spec['operation']=='update' and (type(spec['node_id'])is not int or spec['node_id']<=0):
        raise ValueError('Positive original target identity required')
    return spec


def validate_record(record):
    if not isinstance(record,dict) or set(record)!={'current','tags','history','changeset_owner'}:
        raise ValueError('Complete native database readback required')
    current=record['current']
    if current is None:
        if record['tags'] or record['history'] or record['changeset_owner']is not None:raise ValueError('Inconsistent missing node')
        return None
    for k in ('id','version','changeset_id','latitude','longitude'):
        if type(current.get(k))is not int:raise ValueError('Invalid native node numbers')
    if min(current['id'],current['version'],current['changeset_id'])<=0 or abs(current['latitude'])>900000000 or abs(current['longitude'])>1800000000:
        raise ValueError('Invalid native node identity or location')
    if type(current.get('visible'))is not bool or type(record['changeset_owner'])is not int or record['changeset_owner']<=0:
        raise ValueError('Native visibility and changeset owner required')
    tags=record['tags'];history=record['history']
    if not isinstance(tags,list)or any(not isinstance(t,dict)or t.get('node_id')!=current['id'] or not isinstance(t.get('k'),str)or not isinstance(t.get('v'),str)for t in tags):
        raise ValueError('Invalid persisted tags')
    if len({t['k']for t in tags})!=len(tags):raise ValueError('Duplicate persisted tag')
    if not isinstance(history,list)or not history or any(not isinstance(h,dict)for h in history):raise ValueError('Missing node history')
    versions=[h.get('version')for h in history]
    if any(type(v)is not int for v in versions)or versions!=list(range(1,current['version']+1)) or any(h.get('node_id')!=current['id']for h in history):
        raise ValueError('Incomplete native node version history')
    last=history[-1]
    if any(last.get(k)!=current[k]for k in ('version','changeset_id','latitude','longitude','visible')):
        raise ValueError('Current node disagrees with persisted history')
    return current


def distance_metres(spec,node):
    a,b=math.radians(float(spec['latitude'])),math.radians(node['latitude']/1e7)
    delta=math.radians(node['longitude']/1e7-float(spec['longitude']))
    h=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(delta/2)**2
    return 6371008.8*2*math.asin(math.sqrt(min(1,max(0,h))))


def evaluate(spec,*,initial,final,owner_id,max_initial_node_id,max_initial_changeset_id,runtime_error=None,integrity=True):
    """One selected persisted node, never an arbitrary browser draft.

    For creates the caller locates all bounded post-baseline matching candidates
    and requires an unambiguous target. Boundary maxima come from private initial
    database evidence, not from an actor-provided object ID or edited URL.
    """
    checks={}
    def result(status,reason):return dict(version=VERSION,status=status,reward=None if status=='unknown'else float(status=='success'),checks=checks,reason=reason)
    if runtime_error or integrity is not True:return result('unknown','Execution or state integrity is unverified.')
    try:
        validate_spec(spec)
        if type(owner_id)is not int or owner_id<=0 or any(type(x)is not int or x<0 for x in (max_initial_node_id,max_initial_changeset_id)):
            raise ValueError('Initial account and sequence boundaries required')
        before=validate_record(initial);after=validate_record(final)
        if spec['operation']=='update' and (before is None or before['id']!=spec['node_id'] or before['id']>max_initial_node_id or before['changeset_id']>max_initial_changeset_id):
            raise ValueError('Original update target is not bound to initial state')
        if before:
            old_tags={t['k']:t['v']for t in initial['tags']}
            if all(old_tags.get(k)==v for k,v in spec['tags'].items()) and distance_metres(spec,before)<=spec['tolerance_metres']:
                raise ValueError('Requested change was already satisfied before the task')
        if spec['operation']=='create' and before is not None:raise ValueError('Creation target already existed')
        checks['persisted_target_present']=after is not None
        if after is None:return result('failure','No saved target object was found.')
        checks['correct_object']=(after['id']==spec['node_id']if spec['operation']=='update'else after['id']>max_initial_node_id)
        checks['visible']=after['visible']
        checks['saved_by_task_account']=final['changeset_owner']==owner_id
        checks['post_initial_changeset']=after['changeset_id']>max_initial_changeset_id
        checks['new_version']=(after['version']>before['version']if before else after['version']>=1)
        if before:
            checks['original_history_preserved']=final['history'][:len(initial['history'])]==initial['history']
        actual={t['k']:t['v']for t in final['tags']}
        checks['requested_tags_saved']=all(actual.get(k)==v for k,v in spec['tags'].items())
        checks['requested_location']=distance_metres(spec,after)<=spec['tolerance_metres']
        return result('success'if all(checks.values())else 'failure','Checked the persisted object, requested values, location and version history.')
    except (KeyError,TypeError,ValueError,OverflowError):return result('unknown','Native readback, initial state or explicit task parameters are incomplete.')
