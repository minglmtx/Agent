"""Source-bound node task initialization and bounded persisted result checks."""
from copy import deepcopy
import json
from .map_node_completion import validate_spec,evaluate
from .map_node_readout import capture,validate_snapshot
from .map_node_write_audit import install,read,validate as validate_audit
from .map_reset_guard import STATE_SQL,checked_state,persistent_files
from .map_editor_navigation import prepare_site
from .map_community_fixture import VERSION as COMMUNITY,USERNAME,PASSWORD,records
from .map_native_write_probe import LocalWriteProbe,osm_node
from .io_utils import atomic_write_json

VERSION='explicit-local-map-node-training-v1'
EMPTY=dict(current=None,tags=[],history=[],changeset_owner=None)


def resolve_spec(candidate,initial):
    if candidate.get('candidate_completion',{}).get('family')!='persisted_map_node':
        raise ValueError('Explicit persisted node goal required')
    spec=deepcopy(candidate['candidate_completion']['spec'])
    if spec.get('operation')=='update':
        key=spec.pop('initial_target_key')
        spec['node_id']=initial['fixture_ids'][key]
    return validate_spec(spec)


def environment_key(candidate,profile):
    init=candidate['initialization']
    if (init.get('version')!=VERSION or init.get('account')!=USERNAME
            or init.get('browser_authenticated')is not True
            or init.get('start_path')!=candidate['start_path']
            or candidate.get('map_community_fixture')!=COMMUNITY
            or init.get('task_goal_already_satisfied')is not False):
        raise ValueError('Declared local account, original start and unsatisfied goal required')
    fixtures=init.get('fixtures')
    if not isinstance(fixtures,list)or not 1<=len(fixtures)<=8:
        raise ValueError('Small explicit initialization fixture required')
    keys=[]
    for f in fixtures:
        if set(f)!={'key','latitude','longitude','tags'}or not isinstance(f['key'],str)or not f['key']:
            raise ValueError('Exact native fixture declaration required')
        validate_spec(dict(operation='create',latitude=f['latitude'],longitude=f['longitude'],tags=f['tags'],tolerance_metres=1));keys.append(f['key'])
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate fixture identity')
    return dict(version=VERSION,profile=deepcopy(profile),account=USERNAME,fixtures=deepcopy(fixtures))



def validate_initialization_changes(*,guard,owners,changeset,subscriptions,files_unchanged,community_unchanged):
    allowed={'public.'+n for n in ('users','changesets','changeset_tags','changesets_subscribers',
        'nodes','node_tags','current_nodes','current_node_tags')}
    checked_state(guard)
    expected=[dict(changeset_id=changeset,subscriber_id=next(iter(owners)))]if len(owners)==1 else None
    checks=dict(one_native_owner=len(owners)==1,only_declared_tables_changed=set(guard['changed'])<=allowed,
        exact_native_subscription=expected is not None and subscriptions==expected,
        persistent_files_unchanged=files_unchanged is True,community_records_unchanged=community_unchanged is True)
    return dict(passed=all(checks.values()),checks=checks,changed_tables=guard['changed'],
        expected_changed_tables=sorted(allowed),native_subscriptions=subscriptions)


def prepare(site,candidate,profile,*,browser):
    key=environment_key(candidate,profile)
    old=getattr(site,'_node_task_initialization',None)
    if old is not None:
        if old['environment']!=key:raise ValueError('Node fixture profile changed on reused website')
        site.reset_guard.require_unchanged();audit=read(site)
        if audit['node_ids']or audit['changeset_ids']:raise ValueError('Previously written audit cannot be reused')
        return deepcopy(old)
    prepare_site(site,profile,browser=browser);site.reset_guard.require_unchanged()
    files=persistent_files(site.state/'frontend/app');community=records(site)
    client=LocalWriteProbe(site.url,dict(display_name=USERNAME,password=PASSWORD),site.logs/'node-fixture-native-http')
    def response(method,path,body=None):
        value=client.request(method,path,body)
        if value['status']!=200:raise RuntimeError('Declared native fixture initialization failed')
        return value['response_body']
    changeset=int(response('PUT','/api/0.6/changeset/create','<osm version="0.6"><changeset><tag k="comment" v="Declared isolated training fixture"/></changeset></osm>'))
    ids={f['key']:int(response('PUT','/api/0.6/node/create',osm_node(changeset=changeset,lat=f['latitude'],lon=f['longitude'],tags=f['tags'])))for f in key['fixtures']}
    response('PUT','/api/0.6/changeset/'+str(changeset)+'/close')
    snapshot=capture(site,node_ids=sorted(ids.values()));owners={r['record']['changeset_owner']for r in snapshot['records']}
    guard=checked_state(json.loads(site.app_sql(STATE_SQL)))
    subscriptions=json.loads(site.app_sql("SELECT coalesce(json_agg(x ORDER BY x.subscriber_id),'[]'::json) FROM (SELECT changeset_id,subscriber_id FROM changesets_subscribers WHERE changeset_id="+str(changeset)+")x;"))
    validation=validate_initialization_changes(guard=guard,owners=owners,changeset=changeset,
        subscriptions=subscriptions,files_unchanged=persistent_files(site.state/'frontend/app')==files,
        community_unchanged=records(site)==community)
    atomic_write_json(site.logs/'node-initialization-validation.json',dict(validation,snapshot=snapshot))
    if not validation['passed']:
        raise RuntimeError('Initialization changed outside declared node fixture: '+','.join(k for k,v in validation['checks'].items()if not v))
    by_id={r['node_id']:r['record']for r in snapshot['records']}
    for f in key['fixtures']:
        rec=by_id[ids[f['key']]];node=rec['current']
        if (node['version']!=1 or node['changeset_id']!=changeset or
                {t['k']:t['v']for t in rec['tags']}!=f['tags']or
                node['latitude']!=round(float(f['latitude'])*1e7)or node['longitude']!=round(float(f['longitude'])*1e7)):
            raise RuntimeError('Native fixture differs from declared initial values')
    # This rebase is only for the just-verified declared initializer. Never
    # invoked after an actor episode, and never used to clear dirty task state.
    site.app_sql('TRUNCATE codex_reset_guard.changed;')
    site.reset_guard.initial=site.reset_guard.fingerprint()
    install(site)
    result=dict(environment=key,fixture_ids=ids,snapshot=snapshot,owner_id=owners.pop(),
                baseline=site.fingerprint(),files=files,initialization_changed_tables=guard['changed'])
    atomic_write_json(site.logs/'node-task-initialization.json',result)
    site._node_task_initialization=deepcopy(result)
    return result


def evaluate_set(candidate,initial,audit,final,*,integrity=True,runtime_error=None):
    """Evaluate persisted targets; never infer success from edited URL or draft.

    For creates every touched new ID is read, including wrong values/owners.
    At least one correct new point suffices: the task does not prohibit extra
    points. Wrong edits remain visible in the audit and force a cold rebuild.
    """
    try:
        spec=resolve_spec(candidate,initial);validate_snapshot(initial['snapshot']);validate_audit(audit);validate_snapshot(final)
        before=initial['snapshot'];maximum=before['max_node_id']
        ids=([spec['node_id']]if spec['operation']=='update'else[x for x in audit['node_ids']if x>maximum])
        if [r['node_id']for r in final['records']]!=sorted(ids):raise ValueError('Incomplete touched-target readback')
        initial_record=next((r['record']for r in before['records']if r['node_id']==spec.get('node_id')),EMPTY)
        options=[r['record']for r in final['records']]or[EMPTY]
        checks=[evaluate(spec,initial=initial_record,final=row,owner_id=initial['owner_id'],
            max_initial_node_id=maximum,max_initial_changeset_id=before['max_changeset_id'],
            integrity=integrity,runtime_error=runtime_error)for row in options]
        status='unknown'if any(r['status']=='unknown'for r in checks)else 'success'if any(r['status']=='success'for r in checks)else'failure'
        return dict(version='native-map-node-task-v1',status=status,reward=None if status=='unknown'else float(status=='success'),
            checks=dict(requested_saved_object=any(r['status']=='success'for r in checks)),
            candidates=checks,reason='Checked saved native objects against the declared goal and initial identity.')
    except (KeyError,TypeError,ValueError,RuntimeError):
        return dict(version='native-map-node-task-v1',status='unknown',reward=None,checks={},reason='Bounded native write capture or initial binding is incomplete.')
