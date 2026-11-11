"""Native persisted fork lineage and published repository content checks."""
import hashlib
import time
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint
from .gitlab_project_creation import project_state, validate_state, existing_unchanged

VERSION='gitlab-fork-v1'
ADMISSION_VERSION='gitlab-fork-admission-v1'


def git_state(site, project_id):
    if type(project_id) is not int or project_id<=0:raise ValueError('Invalid Git project identity')
    digest=hashlib.sha256(str(project_id).encode()).hexdigest()
    repo='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
    def git(*args):
        return site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,*args],
            capture_output=True,text=True,timeout=30).stdout.strip()
    return {'refs':git('for-each-ref','--format=%(refname)%09%(objectname)','refs/heads/','refs/tags/').splitlines(),
            'commits':sorted(set(git('rev-list','--branches','--tags').splitlines()))}


def validate_contract(c):
    spec=c.get('fork_creation',{})
    if c.get('domain')!='gitlab' or set(spec)!={'source_id','source_path','own_namespace'} or type(spec['own_namespace']) is not bool or type(spec['source_id']) is not int or spec['source_id']<=0 or not isinstance(spec['source_path'],str) or '/' not in spec['source_path']:
        raise ValueError('Explicit native fork source required')


def fork_state(site,c,username,initial=None,*,settle=False):
    validate_contract(c)
    state=project_state(site,username);source=c['fork_creation']
    matches=[r for r in state['projects'] if r['id']==source['source_id'] and r['full_path']==source['source_path']]
    if len(matches)!=1:raise ValueError('Fork source identity changed')
    state['source_project']=matches[0]
    state['source_git']=git_state(site,source['source_id'])
    if not state['source_git']['refs'] or not state['source_git']['commits']:raise ValueError('Unvalidated empty source repository')
    state['lineages']=select_rows(site,'SELECT project_id,forked_from_project_id FROM fork_network_members ORDER BY project_id')
    if initial is None:
        owned={r['id'] for r in state['projects'] if r['creator_id']==state['user']['id']}
        if any(r['project_id'] in owned and r['forked_from_project_id']==source['source_id'] for r in state['lineages']):
            raise ValueError('Task account already has a fork of the requested source')
        state['new_repositories']={}
        return state
    known={r['id'] for r in initial['projects']}
    new=[r for r in state['projects'] if r['id'] not in known]
    state['new_repositories']={}
    end=time.monotonic()+90
    for project in new:
        ident=project['id']
        while True:
            imports=select_rows(site,f'SELECT project_id,status FROM project_mirror_data WHERE project_id={ident}')
            if len(imports)>1:raise ValueError('Ambiguous native import state')
            status=imports[0]['status'] if imports else None
            if not settle or status not in ('scheduled','started') or time.monotonic()>=end:break
            time.sleep(1)
        # Pending native background work is infrastructure uncertainty, not a
        # model failure and not a reason to invent a completed repository.
        data=git_state(site,ident) if status=='finished' else None
        state['new_repositories'][str(ident)]={'import_status':status,'git':data}
    return state


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','fork_creation','heldout_quarantine','start_revision','goal_revision')})


def protected_unchanged(initial,final):
    return existing_unchanged(initial,final) and initial.get('source_git')==final.get('source_git') and all(r in final.get('lineages',[]) for r in initial.get('lineages',[]))


def evaluate(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    try:
        validate_contract(c);validate_state(initial);validate_state(final)
        for s in (initial,final):
            if not isinstance(s.get('source_git'),dict) or not s['source_git'].get('refs') or not s['source_git'].get('commits') or not isinstance(s.get('lineages'),list) or not isinstance(s.get('new_repositories'),dict):
                raise ValueError('Missing persisted fork state')
            source=s.get('source_project',{})
            if source.get('id')!=c['fork_creation']['source_id'] or source.get('full_path')!=c['fork_creation']['source_path']:
                raise ValueError('Stored fork source does not match the task')
    except (ValueError,KeyError,TypeError) as exc:return unknown(str(exc))
    if final['user']!=initial['user']:return unknown('Fork account changed')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:return unknown('Missing terminal page or transport/server failure')
    old={r['id'] for r in initial['projects']};new=[r for r in final['projects'] if r['id'] not in old]
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'source_and_existing_projects_unchanged':protected_unchanged(initial,final),'one_project_saved':len(new)==1}
    if len(new)==1:
        r=new[0];native=final['new_repositories'].get(str(r['id']))
        if not isinstance(native,dict):return unknown('Missing new repository import state')
        if native.get('import_status') in ('scheduled','started','failed','canceled'):
            return unknown('Native repository import is pending or failed')
        lineage=[x for x in final['lineages'] if x['project_id']==r['id']]
        checks.update(created_by_current_account=r['creator_id']==initial['user']['id'],
            requested_fork_lineage=len(lineage)==1 and lineage[0]['forked_from_project_id']==c['fork_creation']['source_id'],
            native_import_finished=native.get('import_status')=='finished',
            published_repository_copied=native.get('git')==initial['source_git'])
        if c['fork_creation']['own_namespace']:
            checks['saved_to_own_namespace']=r['full_path'].rsplit('/',1)[0]==initial['user']['username']
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls():
    return {**{k:'failure' for k in ('no_op','filled_unsaved','wrong_source','404','login')},
            'positive':'success','saved_then_home':'success'}


def feedback(j):
    labels={'page_valid':'The final page is a valid task website page.',
        'source_and_existing_projects_unchanged':'The source repository and previously existing projects remain unchanged.',
        'one_project_saved':'One new project is saved.',
        'created_by_current_account':'The task account created the copy.',
        'saved_to_own_namespace':'The copy belongs to the task account namespace.',
        'requested_fork_lineage':'The saved copy is a native fork of the requested source.',
        'native_import_finished':'The website has finished importing the fork.',
        'published_repository_copied':'The fork contains the source branches, tags and their reachable commits.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':labels[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def require_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):raise ValueError('Stale or heldout fork admission')
    rows=proof.get('cycles',[])
    if proof.get('passed') is not True or len(rows)!=2 or proof.get('reset_mode')!='fresh_site_per_task_cycle':raise ValueError('Two independent fork controls required')
    for row in rows:
        if row.get('passed') is not True or row.get('initial_valid') is not True or row.get('checks')!=expected_controls() or not row.get('initial_fingerprint') or row.get('protected_unchanged') is not True or row.get('worker_queue')!=['repository_fork']:
            raise ValueError('Incomplete native fork controls')
        validate_state(row.get('initial_state'))
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Independent fork reset baselines differ')
