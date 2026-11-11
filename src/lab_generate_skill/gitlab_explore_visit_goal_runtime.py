"""Explicit exploration completion boundary, recorded without actor guidance.

The task publicly permits the native directory or a project actually listed in
that directory. All judgments run only after termination; no hidden next action.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
from .source_revision_binding import binding,fingerprint,require_source_binding
from .site_navigation_rules import valid_initial_page
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_native_csv_probe import protected_snapshot_session,auth_backup,restore_auth_metadata
from .gitlab_persisted_goal_runtime import refs_snapshot,validate_refs
from .gitlab_directory import project_reference,directory_access_reference,read_directory_page,directory_checks
from .gitlab_section import read_section
from .gitlab_repository import read_repository_page
from .io_utils import atomic_write_json
VERSION='gitlab-explore-visited-native-descendant-v1'
PROOF_VERSION='gitlab-explore-visited-native-two-cold-controls-v1'
SHA=re.compile('[0-9a-f]{64}')
CONTROLS={'initial_no_op','positive_directory','positive_visited_overview','positive_visited_tree','positive_visited_blob','negative_descendant_without_directory','negative_unlisted_or_private_project','negative_dashboard_directory','negative_wrong_section','negative_404','negative_real_login'}


def enabled(c):
    if 'gitlab_explore_visit_goal'not in c:return False
    s=c['gitlab_explore_visit_goal']
    if(c.get('domain')!='gitlab'or c.get('heldout_quarantine')is not False or c.get('eligible_for_training')is not False
       or not isinstance(s,dict)or s.get('version')!=VERSION or s.get('scope')not in ('accessible_nonarchived','public_nonarchived')
       or c.get('completion')!={'family':'gitlab_explore_visit_goal'}or c.get('task_text_changed')is not True
       or c.get('is_explicit_derivative')is not True or c.get('original_benchmark_equivalence')is not False
       or s.get('require_visited_directory_for_descendant')is not True or s.get('record_only_during_rollout')is not True
       or s.get('evaluate_only_after_termination')is not True
       or any(c.get(k)for k in ('query','preferences','gitlab_boundary_goal','gitlab_persisted_goal','gitlab_native_read','gitlab_navigation_goal','gitlab_grouped_goal'))):raise ValueError('Explicit public exploration completion mapping required')
    binding(c);return True


def require_original_binding(c,original,inventory):enabled(c);return require_source_binding(c,original,inventory,domain='gitlab')
def public_goal(c):enabled(c);return c['goal']


def reference(site,c,username):
    enabled(c);access=directory_access_reference(site,username)
    return {'kind':'explore'if c['gitlab_explore_visit_goal']['scope']=='accessible_nonarchived'else'visibility','scope':'explore','reference':project_reference(site),'access_reference':access,**({'levels':[20]}if c['gitlab_explore_visit_goal']['scope']=='public_nonarchived'else{})}


def directory_result(private,state,url):
    checks=directory_checks(private,state,url)
    # Actual All tab, native scope and independent inventory are required for
    # both public and account-accessible versions of the same native directory.
    checks['native_explore_all_tab']=any(t.get('text')=='All'and t.get('path')=='/explore/projects'for t in state.get('tabs',[]))
    return checks


def eligible_projects(private):
    allowed=set(private['access_reference']['project_ids'])
    return {r['path']:r for r in private['reference']if not r['archived']and r['id']in allowed and(private['kind']!='visibility'or r['visibility_level']==20)}


def evaluate(c,page,private,*,site_origin):
    enabled(c)
    checks={'valid_native_terminal':valid_initial_page(page,site_origin=site_origin)}
    if not checks['valid_native_terminal']:return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
    state=page.get('gitlab_explore_visit_goal')
    if not isinstance(state,dict)or not isinstance(state.get('history'),list):return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Complete recorded native visit capture required'}
    checks['bound_task_account']=state.get('current_user_id')==private['access_reference']['user']['id']
    path=unquote(urlsplit(page['url']).path).rstrip('/')
    if path in ('/explore','/explore/projects'):
        checks.update(directory_result(private,state.get('directory',{}),page['url']))
        checks['native_terminal_directory']=state.get('section',{}).get('body_page')=='explore:projects:index'
    else:
        projects=eligible_projects(private);match=next((p for p in projects if path=='/'+p or path.startswith('/'+p+'/-/')),None)
        checks['project_in_declared_collection']=match is not None
        visits=[]
        for event in state['history']:
            try:
                if all(directory_result(private,event['directory'],event['url']).values()):visits.extend(unquote(urlsplit(x['path']).path).strip('/')for x in event['directory']['items'])
            except (ValueError,KeyError,TypeError):continue
        checks['project_actually_listed_in_visited_directory']=match is not None and match in visits
        section=state.get('section',{});repo=state.get('repository',{})
        expected=projects.get(match,{})
        checks['native_project_identity']=section.get('project_ids')==[str(expected.get('id'))]and '/'+str(match)in {r.get('path','').rstrip('/')for r in section.get('breadcrumbs',[])}
        kind='overview'if match is not None and path=='/'+match else'tree'if match is not None and path.startswith('/'+match+'/-/tree/')else'blob'if match is not None and path.startswith('/'+match+'/-/blob/')else None
        # Never accept Issues/settings/README-lookalike pages merely because
        # they carry a project's URL prefix.
        checks['declared_terminal_page_kind']=kind is not None
        checks['native_project_content_loaded']=repo.get('loading')is False and repo.get('wait_status')=='ready'and(
            bool(repo.get('tree_links'))if kind in ('overview','tree')else any(str(x).strip()for x in repo.get('content',[]))if kind=='blob'else False)
        checks['native_repository_page_identity']=section.get('body_page')in ({'projects:show'}if kind=='overview'else{'projects:tree:show','projects:tree:show'}if kind=='tree'else{'projects:blob:show','projects:blob:show'}if kind=='blob'else set())
    passed=all(checks.values());return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks}


def require_admission(c,p):
    enabled(c)
    if(not isinstance(p,dict)or p.get('version')!=PROOF_VERSION or p.get('contract_fingerprint')!=fingerprint(c)or p.get('original_binding')!=binding(c)
       or p.get('actor_attempts')!=0 or p.get('api_calls')!=0 or p.get('formal_preinference_lifecycle_verified')is not True):raise ValueError('Actual source-bound common exploration proof required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two independent cold normal exploration resets required')
    instances=[r.get('fresh_instance_id')for r in cycles]
    if any(not SHA.fullmatch(x or '')for x in instances)or instances[0]==instances[1]:raise ValueError('Distinct normal instances required')
    for cycle in cycles:
        full_snapshot(cycle['protected_before']);full_snapshot(cycle['protected_after']);validate_refs(cycle['refs_before']);validate_refs(cycle['refs_after'])
        if cycle['protected_before']!=cycle['protected_after']or cycle['refs_before']!=cycle['refs_after']or cycle['initial_fingerprint']!=cycle['final_fingerprint']:raise ValueError('Unchanged full16, every native repo ref and reset required')
        controls=cycle.get('controls')
        if not isinstance(controls,dict)or set(controls)!=CONTROLS:raise ValueError('Complete positive/negative exploration controls required')
        for name,row in controls.items():
            if not all(row.get(k)is True for k in ('initial_start_preserved','normal_lifecycle_verified','terminal_integrity','private_feedback_clean')):raise ValueError('Actual common exploration lifecycle incomplete')
            if any(row[k]!=cycle[k]for k in ('private_reference','protected_before','protected_after','refs_before','refs_after')):raise ValueError('Per-control independent native guards differ')
            result=evaluate(c,row['page'],cycle['private_reference'],site_origin=row['site_origin'])
            if result['status']!=('success'if name.startswith('positive')else'failure')or result['status']!=row['judgment']['status']:raise ValueError('Actual terminal exploration control differs: '+name)
            if name=='negative_real_login'and row['page'].get('login_page')is not True:raise ValueError('Real logged-out negative required')
    for key in ('protected_before','refs_before','initial_fingerprint','private_reference'):
        if cycles[0][key]!=cycles[1][key]:raise ValueError('Cold normal baseline differs: '+key)
    return deepcopy(cycles[0])


class ExploreVisitHooks:
    def __init__(self,c,p,directory):
        enabled(c);self.contract=deepcopy(c);self.proof=deepcopy(p);self.directory=Path(directory);self.events=[];self.history=[];self.prepared=False;self.scored=False;self.context=self.initial_page=None
        if p is not None:require_admission(c,p)
    def prepare(self,site,username):
        if self.prepared:raise ValueError('One source normal reset required')
        key=('explore_visit',getattr(site,'generation',0))
        if getattr(site,'_explore_visit_generation',None)!=key:
            import gitlab_native_wiki_cache_init as wiki;import gitlab_native_issue_cache_init as issue
            wiki.initialize(site,self.directory/'wiki-initialization');issue.initialize(site,self.directory/'issue-initialization');site._explore_visit_generation=key
        self.auth=auth_backup(site,username);self.before=protected_snapshot_session(site,self.directory/'protected-before-progress.jsonl');full_snapshot(self.before);self.refs_before=refs_snapshot(site)
        self.reference=reference(site,self.contract,username)
        if self.proof is not None:
            baseline=self.proof['cycles'][0]
            if any(actual!=baseline[k]for k,actual in (('protected_before',self.before),('refs_before',self.refs_before),('private_reference',self.reference))):raise ValueError('Normal exploration reset differs from admitted baseline')
        self.site=site;self.prepared=True;self.events.append('prepare')
    def attach(self,context):
        if not self.prepared or self.context is not None:raise ValueError('One prepared normal context required')
        self.context=context;self.events.append('attach')
    def observe_initial(self,page):
        if self.initial_page is not None or page.context is not self.context or page.url!=self.site.url+self.contract['start_path']:raise ValueError('Exact original first start required')
        self.initial_page=page;self.events.append('observe_initial')
    def record(self,page):
        if self.initial_page is None or page.context is not self.context:raise ValueError('Bound normal observation required')
        if urlsplit(page.url).path.rstrip('/')in ('/explore','/explore/projects'):
            self.history.append({'url':page.url,'directory':read_directory_page(page)})
        self.events.append('record')
    def capture_terminal(self,page,terminal):
        if self.initial_page is None or page.context is not self.context:raise ValueError('Bound common terminal required')
        section=read_section(page);terminal['gitlab_explore_visit_goal']={'current_user_id':page.evaluate('()=>window.gon?.current_user_id??null'),'section':section,'history':deepcopy(self.history)}
        state=terminal['gitlab_explore_visit_goal'];path=urlsplit(page.url).path.rstrip('/')
        if path in ('/explore','/explore/projects'):state['directory']=read_directory_page(page)
        elif section.get('body_page')in ('projects:show','projects:tree:show','projects:blob:show'):state['repository']=read_repository_page(page)
        self.events.append('capture_terminal');atomic_write_json(self.directory/'recorded-native-visits.json',self.history)
    def score_terminal(self,site,page,*,runtime_error=None):
        if not self.prepared or self.scored or site is not self.site:raise ValueError('One terminal judgment required')
        self.scored=True;errors=[];self.after=self.refs_after=None
        try:
            restore_auth_metadata(site,self.auth);self.after=protected_snapshot_session(site,self.directory/'protected-after-progress.jsonl');full_snapshot(self.after);self.refs_after=refs_snapshot(site)
        except Exception as error:errors.append({'exception_type':type(error).__name__})
        integrity=not errors and self.before==self.after and self.refs_before==self.refs_after
        atomic_write_json(self.directory/'explore-private-protection.json',{'protected_before':self.before,'protected_after':self.after,'refs_before':self.refs_before,'refs_after':self.refs_after,'integrity':integrity,'errors':errors,'private_reference':self.reference})
        result={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native capture unavailable'}if runtime_error or errors else evaluate(self.contract,page,self.reference,site_origin=site.url)
        result['checks']['complete_native_protection']=bool(integrity)
        if result['status']!='unknown'and not integrity:result.update(status='failure',reward=0.0)
        self.events.append('score_terminal');atomic_write_json(self.directory/'normal-explore-hook-events.json',self.events);return result,integrity
    def close(self):pass


def feedback(result):return {'status':result.get('status'),'checks':[{'condition':k,'passed':v}for k,v in result.get('checks',{}).items()]}
