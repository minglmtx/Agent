"""Private persisted-group checks; no task answers are exposed to the actor."""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'gitlab-group-creation-v1'
ADMISSION_VERSION = 'gitlab-group-creation-admission-v1'


def validate_contract(c):
    s=c['group_creation']
    if c.get('domain')!='gitlab' or not {'name','visibility_level','top_level'}<=set(s)or set(s)-{'name','visibility_level','top_level','path','settings'}:
        raise ValueError('Unsupported group creation requirements')
    if s['name'] is not None and (not isinstance(s['name'],str) or not s['name'].strip()):
        raise ValueError('Invalid requested group name')
    if s['visibility_level'] is not None and (type(s['visibility_level']) is not int or s['visibility_level'] not in (0,10,20)):
        raise ValueError('Invalid requested group visibility')
    if type(s['top_level']) is not bool:raise ValueError('Invalid top-level condition')
    if 'path'in s:
        import re
        if not isinstance(s['path'],str)or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*',s['path']):raise ValueError('Explicit native group path required')
    if 'settings'in s:
        settings=s['settings']
        if not isinstance(settings,dict)or not settings or set(settings)-{'setup_for_company','jobs_to_be_done'}:
            raise ValueError('Unsupported persisted group settings')
        if 'setup_for_company'in settings and type(settings['setup_for_company'])is not bool:raise ValueError('Group audience must be boolean')
        if 'jobs_to_be_done'in settings and (type(settings['jobs_to_be_done'])is not int or settings['jobs_to_be_done']not in (0,2,3)):
            raise ValueError('Group purpose lacks verified native enum mapping')


def group_state(site,username,contract=None):
    name="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT id,username FROM users WHERE username='+name)
    if len(users)!=1:raise ValueError('Missing or ambiguous group account')
    state={'user':users[0],
        'groups':select_rows(site,"SELECT id,name,path,type,visibility_level,parent_id FROM namespaces WHERE type='Group' ORDER BY id"),
        'members':select_rows(site,"SELECT id,source_id,user_id,access_level FROM members WHERE type='GroupMember' ORDER BY id")}
    if contract and contract['group_creation'].get('settings'):
        validate_contract(contract)
        state['settings']=select_rows(site,"SELECT s.namespace_id,s.setup_for_company,s.jobs_to_be_done FROM namespace_settings s JOIN namespaces n ON n.id=s.namespace_id WHERE n.type='Group' ORDER BY s.namespace_id")
    return state


def validate_initial(c,state):
    validate_contract(c)
    if not isinstance(state,dict) or not state.get('user') or not all(isinstance(state.get(k),list) for k in ('groups','members')):
        raise ValueError('Missing group baseline')
    name=c['group_creation']['name']
    if name and any(r['name']==name for r in state['groups']):raise ValueError('Named group already exists')
    if c['group_creation'].get('path')and any(r['path']==c['group_creation']['path']for r in state['groups']):raise ValueError('Requested group path already exists')
    if c['group_creation'].get('settings'):validate_settings(state)


def validate_settings(state):
    rows=state.get('settings')
    if not isinstance(rows,list)or any(not isinstance(r,dict)or type(r.get('namespace_id'))is not int
        or set(r)!={'namespace_id','setup_for_company','jobs_to_be_done'}
        or (r['setup_for_company']is not None and type(r['setup_for_company'])is not bool)
        or (r['jobs_to_be_done']is not None and type(r['jobs_to_be_done'])is not int)for r in rows):
        raise ValueError('Missing or malformed persisted group settings')
    if len({r['namespace_id']for r in rows})!=len(rows):raise ValueError('Duplicate group settings identity')
    return {r['namespace_id']:r for r in rows}


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path',
        'group_creation','heldout_quarantine','start_revision','goal_revision')})


def evaluate_group(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    try:validate_initial(c,initial)
    except (ValueError,KeyError,TypeError) as exc:return unknown(str(exc))
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    if not isinstance(final,dict) or final.get('user')!=initial['user'] or not all(isinstance(final.get(k),list) for k in ('groups','members')):
        return unknown('Missing group state or changed account')
    if c['group_creation'].get('settings'):
        try:old_settings=validate_settings(initial);new_settings=validate_settings(final)
        except ValueError as exc:return unknown(str(exc))
    old={r['id']:r for r in initial['groups']};current={r['id']:r for r in final['groups']}
    members={r['id']:r for r in initial['members']};now_members={r['id']:r for r in final['members']}
    new=[r for r in final['groups'] if r['id'] not in old]
    new_members=[r for r in final['members'] if r['id'] not in members]
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
        'existing_groups_unchanged':all(current.get(k)==v for k,v in old.items()),
        'existing_memberships_unchanged':all(now_members.get(k)==v for k,v in members.items()),
        'one_group_saved':len(new)==1}
    if c['group_creation'].get('settings'):
        checks['existing_group_settings_unchanged']=all(new_settings.get(k)==v for k,v in old_settings.items())
        checks['no_unrelated_group_settings_added']=set(new_settings)-set(old_settings)<={r['id']for r in new}
    if len(new)==1:
        row=new[0];s=c['group_creation']
        checks.update(requested_name=s['name'] is None or row['name']==s['name'],
            requested_visibility=s['visibility_level'] is None or row['visibility_level']==s['visibility_level'],
            requested_hierarchy=not s['top_level'] or row['parent_id'] is None,
            native_fields_saved=all(isinstance(row[k],str) and bool(row[k].strip()) for k in ('name','path')),
            owned_by_current_account=any(m['source_id']==row['id'] and m['user_id']==initial['user']['id'] and m['access_level']==50 for m in new_members),
            no_unrelated_membership_added=all(m['source_id']==row['id'] for m in new_members))
        if 'path'in s:checks['requested_path']=row['path']==s['path']
        for key,value in s.get('settings',{}).items():
            checks['requested_'+key]=new_settings.get(row['id'],{}).get(key)==value
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls(c):
    checks={k:'failure' for k in ('no_op','filled_unsaved','invalid_form','404','login')}
    checks.update(positive='success',saved_then_home='success')
    if c['group_creation']['name'] is not None:checks['wrong_name']='failure'
    if c['group_creation']['visibility_level'] is not None:checks['wrong_visibility']='failure'
    if 'path'in c['group_creation']:checks['wrong_path']='failure'
    for key in c['group_creation'].get('settings',{}):checks['wrong_'+key]='failure'
    return checks


def group_feedback(j):
    labels={'page_valid':'The final page is a valid page on the task website.',
        'existing_groups_unchanged':'Previously existing groups remain unchanged.',
        'existing_memberships_unchanged':'Previously existing group memberships remain unchanged.',
        'one_group_saved':'One new group has actually been saved.',
        'requested_name':'The saved name satisfies the task requirement.',
        'requested_visibility':'The saved visibility satisfies the task requirement.',
        'requested_hierarchy':'The saved group hierarchy satisfies the task requirement.',
        'native_fields_saved':'The native required group fields were saved.',
        'owned_by_current_account':'The created group belongs to the current account.',
        'existing_group_settings_unchanged':'Previously existing group settings remain unchanged.',
        'no_unrelated_group_settings_added':'No settings record was added for an unrelated group.',
        'requested_path':'The saved group URL satisfies the task requirement.',
        'requested_setup_for_company':'The saved group audience satisfies the task requirement.',
        'requested_jobs_to_be_done':'The saved group purpose satisfies the task requirement.',
        'no_unrelated_membership_added':'No membership in an unrelated group was added.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':labels[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def require_group_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Stale or quarantined group admission')
    rows=proof.get('cycles',[])
    if proof.get('passed') is not True or len(rows)!=2 or proof.get('reset_mode')!='fresh_site_per_task_cycle':
        raise ValueError('Two independent group control cycles required')
    for row in rows:
        validate_initial(c,row.get('initial_state'))
        if row.get('passed') is not True or row.get('initial_valid') is not True or row.get('checks')!=expected_controls(c):
            raise ValueError('Incomplete native group controls')
        if not row.get('initial_fingerprint') or row['initial_fingerprint']!=row.get('final_fingerprint'):
            raise ValueError('Protected projects changed')
        for name in ('wrong_name','wrong_visibility','wrong_path','wrong_setup_for_company','wrong_jobs_to_be_done'):
            if name in expected_controls(c):
                wrong=row.get('independent_negatives',{}).get(name,{})
                if wrong.get('initial_state')!=row['initial_state'] or wrong.get('isolated_wrong_condition') is not True or wrong.get('protected_projects_unchanged') is not True:
                    raise ValueError('Wrong group control was not independently isolated')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Independent group reset baselines differ')
