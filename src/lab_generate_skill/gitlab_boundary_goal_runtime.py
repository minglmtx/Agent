"""Source-bound terminal navigation/content lifecycle for old boundary repairs.

Reuse the existing independent evaluator; bind its exact configuration to a
normal proof. No hidden scope is added to actor observations or task strategy.
"""
from copy import deepcopy
import json,re
from pathlib import Path
from .source_revision_binding import binding,fingerprint,require_source_binding
from .site_navigation_rules import evaluate_navigation,valid_initial_page
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_native_csv_probe import protected_snapshot_session,auth_backup,restore_auth_metadata
from .gitlab_persisted_goal_runtime import refs_snapshot,validate_refs
from .io_utils import atomic_write_json

VERSION='gitlab-boundary-normal-runtime-v1'
PROOF_VERSION='gitlab-boundary-normal-two-cold-controls-v1'
CACHE_PROOF_VERSION='gitlab-boundary-normal-native-issue-certification-two-cold-v2'
SHA=re.compile('[0-9a-f]{64}')


def enabled(c):
    if 'gitlab_boundary_goal'not in c:return False
    s=c['gitlab_boundary_goal']
    if (c.get('domain')!='gitlab' or c.get('heldout_quarantine')is not False
            or c.get('eligible_for_training')is not False or not isinstance(s,dict)
            or s.get('version')!=VERSION or s.get('kind')not in ('page_navigation','native_document')
            or s.get('initial_status')not in ('success','failure')
            or c.get('allow_initial_success')!=(s['initial_status']=='success')
            or not isinstance(s.get('required_controls'),list)
            or not {'initial_no_op','positive','wrong_target','404','login'}<=set(s['required_controls'])
            or len(s['required_controls'])!=len(set(s['required_controls']))
            or any(k not in {'initial_no_op','positive','positive_alias','wrong_target','wrong_section','404','login'}for k in s['required_controls'])
            or any(c.get(k)for k in ('gitlab_grouped_goal','gitlab_navigation_goal','gitlab_persisted_goal','gitlab_native_read','query','preferences','repository_download'))):raise ValueError('Explicit source-bound terminal navigation boundary required')
    if (s['kind']=='native_document')!=(c.get('completion',{}).get('family')=='gitlab_native_content'):raise ValueError('Declared native content evaluator differs')
    binding(c)
    if s['kind']=='native_document':
        from .gitlab_native_content import load_reference
        load_reference(c)
    return True


def require_original_binding(c,original,inventory):
    enabled(c);return require_source_binding(c,original,inventory,domain='gitlab')


def public_goal(c):enabled(c);return c['goal']


def evaluate(c,page,site_origin):
    enabled(c);r=evaluate_navigation(c,page,site_origin=site_origin);r['version']=VERSION;return r


def _require_legacy_admission(c,p):
    enabled(c)
    if (p.get('version')!=PROOF_VERSION or p.get('contract_fingerprint')!=fingerprint(c)
            or p.get('original_binding')!=binding(c) or p.get('actor_attempts')!=0 or p.get('api_calls')!=0
            or p.get('formal_preinference_lifecycle_verified')is not True):raise ValueError('Actual source-bound common lifecycle proof required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two fresh navigation resets required')
    instances=[r.get('fresh_instance_id') for r in cycles]
    if any(not SHA.fullmatch(x or '')for x in instances)or instances[0]==instances[1]:raise ValueError('Independent fresh navigation deployments required')
    for cycle in cycles:
        full_snapshot(cycle['protected_before']);full_snapshot(cycle['protected_after']);validate_refs(cycle['refs_before']);validate_refs(cycle['refs_after'])
        if (cycle['protected_before']!=cycle['protected_after']or cycle['refs_before']!=cycle['refs_after']
                or cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')or not SHA.fullmatch(cycle.get('initial_fingerprint',''))
                or cycle.get('native_cache_initialization_verified')is not True):raise ValueError('Complete unchanged DB/ref native boundary baseline required')
        controls=cycle.get('controls')
        if not isinstance(controls,dict)or set(controls)!=set(c['gitlab_boundary_goal']['required_controls']):raise ValueError('Exact positive/negative/initial boundary controls required')
        for name,row in controls.items():
            if (row.get('initial_start_preserved')is not True or row.get('normal_lifecycle_verified')is not True
                    or row.get('terminal_integrity')is not True or row.get('private_feedback_clean')is not True
                    or row.get('protected_before')!=cycle['protected_before']or row.get('protected_after')!=cycle['protected_after']
                    or row.get('refs_before')!=cycle['refs_before']or row.get('refs_after')!=cycle['refs_after']):raise ValueError('Actual unchanged common terminal lifecycle required')
            if name in ('initial_no_op','wrong_target','wrong_section')and not valid_initial_page(row['page'],site_origin=row['site_origin']):raise ValueError('Actual initial and wrong object must be healthy native pages')
            expected=c['gitlab_boundary_goal']['initial_status']if name=='initial_no_op'else'success'if name.startswith('positive')else'failure'
            observed=evaluate(c,row['page'],row['site_origin'])
            if observed['status']!=expected or row['judgment'].get('status')!=observed['status']:raise ValueError('Actual native terminal boundary result differs: '+name)
            if name=='login'and row['page'].get('login_page')is not True:raise ValueError('Authenticated redirect cannot be a login negative')
    for key in ('protected_before','refs_before','initial_fingerprint'):
        if cycles[0][key]!=cycles[1][key]:raise ValueError('Fresh navigation reset differs: '+key)
    return deepcopy(cycles[0])


def _require_issue_guard(row):
    """Preserve complete raw state; certify only exact observed native renders."""
    from gitlab_issue_cache_normal_protection import verify_evidence
    full_snapshot(row['protected_before']);full_snapshot(row['protected_after'])
    validate_refs(row['refs_before']);validate_refs(row['refs_after'])
    if row['refs_before']!=row['refs_after']or row.get('integrity')is not True or row.get('errors')!=[]:
        raise ValueError('Complete native repository refs or terminal guard changed')
    evidence=row.get('native_issue_cache_evidence')
    if row['protected_before']==row['protected_after']:
        if evidence is not None or row.get('refs_after_readonly_renderer')is not None:
            raise ValueError('Unchanged full16 guard must not invent a renderer certificate')
        return
    if not isinstance(evidence,dict):raise ValueError('Actual complete native issue evidence required for changed full16')
    if not isinstance(row.get('native_account_username'),str)or not re.fullmatch(r'[\w.-]+',row['native_account_username'])or type(row.get('native_account_id'))is not int or row['native_account_id']<1:
        raise ValueError('Exact native control authentication identity required')
    if evidence.get('witness')!=row.get('actual_issue_document_witness'):
        raise ValueError('Renderer certificate witness differs from actual normal control document')
    verify_evidence(evidence,row['protected_before'],row['protected_after'],site_origin=row['site_origin'],username=row['native_account_username'],account_id=row['native_account_id'])
    validate_refs(row['refs_after_readonly_renderer'])
    if row['refs_after_readonly_renderer']!=row['refs_after']:
        raise ValueError('Readonly native renderer changed complete repository refs')


def require_admission(c,p):
    """Existing v1 proofs retain their exact strict gate; v2 adds certification."""
    if p.get('version')==PROOF_VERSION:return _require_legacy_admission(c,p)
    enabled(c)
    if (p.get('version')!=CACHE_PROOF_VERSION or p.get('contract_fingerprint')!=fingerprint(c)
            or p.get('original_binding')!=binding(c)or p.get('actor_attempts')!=0 or p.get('api_calls')!=0
            or p.get('formal_preinference_lifecycle_verified')is not True):
        raise ValueError('Actual source-bound complete native issue lifecycle proof required')
    account=p.get('native_account')
    if not isinstance(account,dict)or set(account)!={'username','id'}or not isinstance(account['username'],str)or not re.fullmatch(r'[\w.-]+',account['username'])or type(account['id'])is not int or account['id']<1:
        raise ValueError('Actual frozen native authentication identity required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two fresh navigation resets required')
    instances=[r.get('fresh_instance_id')for r in cycles]
    if any(not SHA.fullmatch(x or '')for x in instances)or instances[0]==instances[1]:
        raise ValueError('Independent fresh navigation deployments required')
    for cycle in cycles:
        full_snapshot(cycle['protected_before']);full_snapshot(cycle['protected_after'])
        validate_refs(cycle['refs_before']);validate_refs(cycle['refs_after'])
        if (cycle.get('source_task_id')!=c['source_task_id']
                or cycle['refs_before']!=cycle['refs_after']
                or cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')
                or not SHA.fullmatch(cycle.get('initial_fingerprint',''))
                or cycle.get('native_cache_initialization_verified')is not True):
            raise ValueError('Complete native project/repository reset boundary required')
        controls=cycle.get('controls')
        if not isinstance(controls,dict)or list(controls)!=c['gitlab_boundary_goal']['required_controls']:
            raise ValueError('Exact ordered positive/negative/initial boundary controls required')
        current=cycle['protected_before']
        for name,row in controls.items():
            if (row.get('initial_start_preserved')is not True or row.get('normal_lifecycle_verified')is not True
                    or row.get('terminal_integrity')is not True or row.get('private_feedback_clean')is not True
                    or row.get('native_account_username')!=account['username']or row.get('native_account_id')!=account['id']
                    or row['protected_before']!=current or row['refs_before']!=cycle['refs_before']
                    or row['refs_after']!=cycle['refs_after']):
                raise ValueError('Actual complete normal boundary state transition required')
            _require_issue_guard(row);current=row['protected_after']
            if name in('initial_no_op','wrong_target','wrong_section')and not valid_initial_page(row['page'],site_origin=row['site_origin']):
                raise ValueError('Actual initial and wrong object must be healthy native pages')
            expected=c['gitlab_boundary_goal']['initial_status']if name=='initial_no_op'else'success'if name.startswith('positive')else'failure'
            observed=evaluate(c,row['page'],row['site_origin'])
            if observed['status']!=expected or row['judgment'].get('status')!=observed['status']:
                raise ValueError('Actual native terminal boundary result differs: '+name)
            if name=='login'and row['page'].get('login_page')is not True:raise ValueError('Authenticated redirect cannot be a login negative')
        if current!=cycle['protected_after']:raise ValueError('Complete final state is not the actual certified control chain')
    for key in('protected_before','refs_before','initial_fingerprint'):
        if cycles[0][key]!=cycles[1][key]:raise ValueError('Fresh navigation reset differs: '+key)
    return deepcopy(cycles[0])


class BoundaryGoalHooks:
    def __init__(self,c,p,directory):
        enabled(c);self.contract=deepcopy(c);self.proof=deepcopy(p);self.directory=Path(directory);self.events=[];self.prepared=False;self.scored=False;self.context=None;self.initial_page=None
        if p is not None:require_admission(c,p)
    def prepare(self,site,username):
        if self.prepared:raise ValueError('One normal boundary source reset required')
        key=('boundary',getattr(site,'generation',0))
        if getattr(site,'_boundary_generation',None)!=key:
            import gitlab_native_wiki_cache_init as wiki;import gitlab_native_issue_cache_init as issue
            wiki.initialize(site,self.directory/'wiki-initialization');issue.initialize(site,self.directory/'issue-initialization');site._boundary_generation=key
        self.auth=auth_backup(site,username);self.username=username;self.before=protected_snapshot_session(site,self.directory/'protected-before-progress.jsonl');full_snapshot(self.before);self.refs_before=refs_snapshot(site)
        from gitlab_issue_cache_normal_protection import NativeIssueProtection
        self.issue_protection=NativeIssueProtection(site,username,self.directory/'native-issue-protection',full_baseline=self.before)
        if self.contract['gitlab_boundary_goal']['kind']=='native_document':
            from .gitlab_native_content import load_reference,verify_reference
            reference=load_reference(self.contract);verify_reference(site,reference)
        if self.proof is not None:
            baseline=self.proof['cycles'][0]
            if self.before!=baseline['protected_before']or self.refs_before!=baseline['refs_before']:raise ValueError('Actual normal reset differs from admitted native boundaries')
        self.site=site;self.prepared=True;self.events.append('prepare')
    def attach(self,context):
        if not self.prepared or self.context is not None:raise ValueError('One prepared native browser context required')
        self.context=context;self.issue_protection.attach(context);self.events.append('attach')
    def observe_initial(self,page):
        if self.initial_page is not None or page.context is not self.context or page.url!=self.site.url+self.contract['start_path']:raise ValueError('Exact bound source initial page required')
        self.initial_page=page;self.issue_protection.observe(page);self.events.append('observe_initial')
    def record(self,page):
        if self.initial_page is None or page.context is not self.context:raise ValueError('Bound normal observation required')
        self.issue_protection.observe(page);self.events.append('record')
    def capture_terminal(self,page,terminal):
        if self.initial_page is None or page.context is not self.context:raise ValueError('Bound native terminal page required')
        if self.contract['gitlab_boundary_goal']['kind']=='native_document':
            from .gitlab_native_content import read_terminal
            terminal['gitlab_native_content']=read_terminal(page,self.contract,site_origin=self.site.url)
        self.events.append('capture_terminal')
    def score_terminal(self,site,page,*,runtime_error=None):
        if not self.prepared or self.scored or site is not self.site:raise ValueError('One terminal native boundary judgment required')
        self.scored=True;errors=[];self.after=self.refs_after=None;issue_evidence=None;refs_after_renderer=None;witness=None
        try:
            restore_auth_metadata(site,self.auth);self.after=protected_snapshot_session(site,self.directory/'protected-after-progress.jsonl');full_snapshot(self.after);self.refs_after=refs_snapshot(site)
            if self.before!=self.after:
                self.issue_protection.certify_terminal(self.after)
                issue_evidence=self.issue_protection.terminal_evidence
                refs_after_renderer=refs_snapshot(site)
                if refs_after_renderer!=self.refs_after:raise ValueError('Readonly native renderer changed complete repository refs')
            witness=self.issue_protection.witness.record()
        except Exception as error:errors.append({'exception_type':type(error).__name__})
        integrity=not errors and self.refs_before==self.refs_after and(self.before==self.after or issue_evidence is not None)
        atomic_write_json(self.directory/'boundary-private-protection.json',{'protected_before':self.before,'protected_after':self.after,'refs_before':self.refs_before,'refs_after':self.refs_after,'integrity':integrity,'errors':errors,'native_issue_cache_evidence':issue_evidence,'refs_after_readonly_renderer':refs_after_renderer,'native_account_username':self.username,'native_account_id':self.issue_protection.witness.account_id,'actual_issue_document_witness':witness})
        result={'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native runtime/capture unavailable'}if runtime_error or errors else evaluate(self.contract,page,site.url)
        result['checks']['complete_native_protection']=bool(integrity)
        if result['status']!='unknown'and not integrity:result.update(status='failure',reward=0.0)
        self.events.append('score_terminal');atomic_write_json(self.directory/'normal-boundary-hook-events.json',self.events);return result,integrity
    def close(self):pass


def feedback(result):
    return {'status':result.get('status'),'checks':[{'condition':k,'passed':v}for k,v in result.get('checks',{}).items()]}
