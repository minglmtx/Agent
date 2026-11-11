"""Terminal native project persistence checks, independent of actor claims."""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='gitlab-project-creation-v1'
ADMISSION_VERSION='gitlab-project-creation-admission-v1'


def validate_contract(c):
    if c.get('domain')!='gitlab' or c.get('project_creation')!={'kind':'blank'}:
        raise ValueError('Only unconstrained original blank-project creation is admitted')


def project_state(site, username):
    name="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT id,username FROM users WHERE username='+name)
    if len(users)!=1:raise ValueError('Missing or ambiguous project account')
    return {'user':users[0], 'projects':select_rows(site,
        "SELECT p.id,p.name,p.path,p.namespace_id,p.creator_id,p.visibility_level,r.path AS full_path "
        "FROM projects p JOIN routes r ON r.source_id=p.id AND r.source_type='Project' ORDER BY p.id")}


def validate_state(state):
    if not isinstance(state,dict) or not isinstance(state.get('user'),dict) or type(state['user'].get('id')) is not int:
        raise ValueError('Missing project account state')
    rows=state.get('projects')
    fields={'id','name','path','namespace_id','creator_id','visibility_level','full_path'}
    if not isinstance(rows,list) or any(not isinstance(r,dict) or set(r)!=fields or type(r['id']) is not int for r in rows):
        raise ValueError('Incomplete persisted project state')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate project identity')


def existing_unchanged(initial, final):
    validate_state(initial);validate_state(final)
    current={r['id']:r for r in final['projects']}
    return final['user']==initial['user'] and all(current.get(r['id'])==r for r in initial['projects'])


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal',
        'start_path','project_creation','heldout_quarantine','start_revision','goal_revision')})


def evaluate_project(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    try:validate_contract(c);validate_state(initial);validate_state(final)
    except (ValueError,KeyError,TypeError) as exc:return unknown(str(exc))
    if final['user']!=initial['user']:return unknown('Project account changed')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    old={r['id'] for r in initial['projects']}
    new=[r for r in final['projects'] if r['id'] not in old]
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
        'existing_projects_unchanged':existing_unchanged(initial,final), 'one_project_saved':len(new)==1}
    if len(new)==1:
        r=new[0]
        checks.update(created_by_current_account=r['creator_id']==initial['user']['id'],
            native_identity_saved=all(isinstance(r[k],str) and bool(r[k].strip()) for k in ('name','path','full_path')))
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls():
    return {**{k:'failure' for k in ('no_op','filled_unsaved','invalid_form','404','login')},
            **{k:'success' for k in ('positive','saved_then_home')}}


def feedback(j):
    labels={'page_valid':'The final page is a valid page on the task website.',
        'existing_projects_unchanged':'Previously existing projects remain unchanged.',
        'one_project_saved':'One new project was actually saved.',
        'created_by_current_account':'The new project was created by the task account.',
        'native_identity_saved':'The new project has its native name, path and route saved.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':labels[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def require_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Stale or heldout project admission')
    rows=proof.get('cycles',[])
    if proof.get('passed') is not True or len(rows)!=2 or proof.get('reset_mode')!='fresh_site_per_task_cycle':
        raise ValueError('Two independent project control cycles required')
    for row in rows:
        validate_state(row.get('initial_state'))
        if row.get('passed') is not True or row.get('initial_valid') is not True or row.get('checks')!=expected_controls():
            raise ValueError('Incomplete native project controls')
        if row.get('existing_projects_unchanged') is not True or not row.get('initial_fingerprint'):
            raise ValueError('Existing project integrity evidence required')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Independent project reset baselines differ')
