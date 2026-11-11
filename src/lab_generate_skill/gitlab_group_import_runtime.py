"""Terminal-only ordinary browser hooks for a declared local metadata import.

A candidate implementation is not an admission: the formal gate independently
rescoring raw normal controls below must pass before the actor factory is used.
"""
from copy import deepcopy
from pathlib import Path
import re,time
import psutil
from . import gitlab_group_import as rule
from .gitlab_group_import_state import capture,group_projection
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_persisted_goal_runtime import validate_refs
from .source_revision_binding import binding,fingerprint,require_source_binding
from .browser_assets import BrowserUploadFile,upload_file_metadata
from .io_utils import atomic_write_json as save

VERSION=rule.VERSION
FEEDBACK_VERSIONS=(VERSION,)
PROOF_VERSION='gitlab-local-group-import-normal-controls-v1'
AUTHORIZED_TARGET_WRITES=True
CONTROLS={'no_op':'failure','unsaved':'failure','wrong_path':'failure','missing_metadata':'failure','positive':'success'}


def enabled(c):
    if 'group_import'not in c:return False
    rule.validate_contract(c)
    if c.get('eligible_for_training')is not False:raise ValueError('Candidate gate is not a dataset publication')
    if any(c.get(k)for k in ('group_creation','gitlab_persisted_goal','gitlab_native_read','query','preferences')):
        raise ValueError('One terminal completion protocol required')
    return True


def require_original_binding(c,original,inventory):
    enabled(c);return require_source_binding(c,original,inventory,domain='gitlab')


def guard(value):
    if not isinstance(value,dict)or set(value)!={'tables','extra_relations','repositories'}:
        raise ValueError('Complete non-target native guard required')
    full_snapshot(value['tables']);validate_refs(value['repositories'])
    if set(value['extra_relations'])!={'namespace_settings','group_import_states'}:
        raise ValueError('Complete native import relation protection required')
    for name,key in [('namespace_settings','namespace_id'),('group_import_states','group_id')]:
        rows=value['extra_relations'][name]
        if not isinstance(rows,list)or any(set(r)!={key,'md5'}or type(r[key])is not int or not re.fullmatch('[0-9a-f]{32}',r['md5'])for r in rows):
            raise ValueError('Malformed native import relation protection')
        if len({r[key]for r in rows})!=len(rows):raise ValueError('Duplicate protected relation identity')
    return value


def score(c,reference,page,initial,final,*,origin,enums,error=None):
    try:
        old=guard(initial['guard']);new=guard(final['guard'])
        result=rule.evaluate(c,reference,page,initial['state'],final['state'],site_origin=origin,
            finished_status=enums['finished'],pending_statuses=[enums['created'],enums['started']],runtime_error=error)
        intact=old==new
        if result['status']!='unknown':
            result['checks']['non_target_native_state_unchanged']=intact
            if not intact:result.update(status='failure',reward=0.0)
        return result,intact
    except (KeyError,ValueError,TypeError)as exc:
        return dict(version=VERSION,status='unknown',reward=None,checks={},reason=str(exc)),False


def require_cycle(c,reference,cycle):
    """Rescore one complete archived cycle; alone it never grants admission."""
    enabled(c)
    if not isinstance(cycle,dict) or not re.fullmatch('[0-9a-f]{64}',str(cycle.get('fresh_instance_id',''))):
        raise ValueError('Bound independent native instance required')
    if set(cycle.get('controls',{}))!=set(CONTROLS):raise ValueError('Missing normal positive/negative controls')
    for name,entry in cycle['controls'].items():
        result,intact=score(c,reference,entry['page'],entry['initial'],entry['final'],origin=entry['origin'],enums=entry['enums'])
        if result!=entry['judgment']or result['status']!=CONTROLS[name]:raise ValueError('Raw native control does not support its recorded outcome')
        if name in ('no_op','unsaved','positive')and not intact:raise ValueError('Unrelated native state changed')
        if entry.get('events',[])[:3]!=['prepare','attach','observe_initial']or entry['events'][-2:]!=['capture_terminal','score_terminal']:
            raise ValueError('Actual terminal-only ordinary lifecycle required')
        if entry.get('initial_start_preserved')is not True or entry.get('worker_stopped')is not True:
            raise ValueError('Initial-state or background-worker cleanup proof missing')
        if name=='positive'and entry.get('declared_upload_used')is not True:
            raise ValueError('Normal declared-file upload action was not tested')
    initial=cycle['controls']['no_op']['initial']
    if cycle.get('reset_capture')!=initial:raise ValueError('Full native import reset differs')
    if cycle.get('pending_imports_after_reset')!=0:raise ValueError('Background work survived reset')
    return cycle


def require_admission(c,p):
    enabled(c)
    from .archived_json_evidence import load
    p=load(p)
    controlled={k:v for k,v in c.items()if k!='admission_result'}
    if (p.get('version')!=PROOF_VERSION or p.get('contract_fingerprint')!=fingerprint(controlled)
            or p.get('source_binding')!=binding(c)or p.get('actor_attempts')!=0 or p.get('api_calls')!=0):
        raise ValueError('Bound original normal controls required')
    rule.verify_asset(c,p['reference'],p['asset'])
    cycles=p.get('cycles');identities=set()
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two independent normal reset cycles required')
    for cycle in cycles:
        require_cycle(c,p['reference'],cycle)
        identity=cycle['fresh_instance_id']
        if identity in identities:raise ValueError('Independent native instances required')
        identities.add(identity)
    if cycles[0]['controls']['no_op']['initial']!=cycles[1]['controls']['no_op']['initial']:
        raise ValueError('Fresh native task starts differ')
    return p


def installed_enums(site):
    text=site.command(['cat','/opt/gitlab/embedded/service/gitlab-rails/app/models/group_import_state.rb'],capture_output=True,text=True,timeout=20).stdout
    values={}
    for name in ('created','started','finished'):
        found=re.findall(r'^\s*state :'+name+r', value: (\d+)\s*$',text,re.M)
        if len(found)!=1:raise ValueError('Installed import state mapping missing: '+name)
        values[name]=int(found[0])
    if len(set(values.values()))!=3:raise ValueError('Ambiguous native state mapping')
    return values


class GroupImportHooks:
    def __init__(self,c,reference,asset,directory):
        enabled(c);rule.verify_asset(c,reference,asset)
        self.contract=deepcopy(c);self.reference=deepcopy(reference);self.asset=str(Path(asset).resolve());self.directory=Path(directory)
        self.context=None;self.events=[];self.initial_page=None;self.prepared=False;self.scored=False;self.worker=None;self.final=None
    def prepare(self,site,username):
        if self.prepared:raise ValueError('One import attempt per reset')
        self.site=site;self.generation=site.generation;self.directory.mkdir(parents=True,exist_ok=True)
        self.enums=installed_enums(site)
        self.initial=capture(site,self.contract['group_import']['path'],progress=self.directory/'initial-protection-progress.jsonl')
        if self.initial['state']['target']is not None:raise ValueError('Import destination already exists')
        from .gitlab_background import start
        start(site,queue='group_import');self.worker=site.processes[-1]
        self.worker_children=psutil.Process(self.worker.pid).children(recursive=True)
        self.prepared=True;self.events.append('prepare')
    def attach(self,context):
        if not self.prepared or self.context is not None:raise ValueError('One actual prepared browser context required')
        self.context=context;self.events.append('attach')
    def observe_initial(self,page):
        if self.initial_page is not None or page.context is not self.context or page.url!=self.site.url+self.contract['start_path']:
            raise ValueError('Exact source initial browser page required')
        self.initial_page=page;self.events.append('observe_initial')
    def record(self,page):
        if page.context is not self.context or self.initial_page is None:raise ValueError('Bound current browser observation required')
        self.events.append('record')
    def _stop_worker(self):
        if self.worker is None:return
        if self.worker.poll()is None:
            self.worker_children.extend(psutil.Process(self.worker.pid).children(recursive=True))
            self.worker.terminate()
            self.worker.wait(timeout=30)
        # Full descendant cleanup/reset still belongs to SiteWorker. This hook
        # refuses to claim a quiet terminal if the native worker did not exit.
        _,alive=psutil.wait_procs(self.worker_children,timeout=20)
        alive=[p for p in alive if p.is_running()and p.status()!=psutil.STATUS_ZOMBIE]
        if alive:raise RuntimeError('Owned native import descendants did not stop')
        self.worker_stopped=self.worker.poll()is not None
    def capture_terminal(self,page,terminal):
        if page.context is not self.context or self.initial_page is None or self.final is not None or self.site.generation!=self.generation:
            raise ValueError('One bound terminal after the actual attempt required')
        end=time.monotonic()+90;self.capture_error=None
        try:
            while True:
                target=group_projection(self.site,self.contract['group_import']['path'])
                pending=target is not None and any(r['status']in(self.enums['created'],self.enums['started'])for r in target['native_import_states'])
                if not pending:break
                if self.worker.poll()is not None:raise RuntimeError('Native import worker exited before completion')
                if time.monotonic()>=end:raise TimeoutError('Native import did not settle within 90 seconds')
                time.sleep(1)
            self._stop_worker()
            self.final=capture(self.site,self.contract['group_import']['path'],progress=self.directory/'terminal-protection-progress.jsonl',initial=self.initial)
        except Exception as error:self.capture_error=type(error).__name__
        finally:
            try:self._stop_worker()
            except Exception as error:
                self.capture_error=type(error).__name__
                raise
            finally:
                self.events.append('capture_terminal')
                # Preserve captured state even if a control/actor raises before
                # score_terminal. One atomic file is replaced after scoring;
                # an unscored capture is never a positive or negative reward.
                self._save_terminal(completed=False)
    def _save_terminal(self,*,completed,judgment=None):
        save(self.directory/'private-group-import-terminal.json',dict(
            initial=self.initial,final=self.final,enums=self.enums,
            judgment=judgment,events=self.events,
            worker_stopped=getattr(self,'worker_stopped',False),
            capture_error=getattr(self,'capture_error',None),
            terminal_score_completed=completed))
    def close(self):self._stop_worker()
    def score_terminal(self,site,page,*,runtime_error=None):
        if self.scored or site is not self.site or site.generation!=self.generation:raise ValueError('One terminal score on original native reset')
        self.scored=True
        result,intact=score(self.contract,self.reference,page,self.initial,self.final,origin=site.url,enums=self.enums,error=runtime_error or self.capture_error)
        self.events.append('score_terminal')
        self._save_terminal(completed=True,judgment=result)
        return result,intact


def NativeReadHooks(c,p,directory):
    p=require_admission(c,p)
    return GroupImportHooks(c,p['reference'],p['asset'],directory)


def upload_files(c,hooks):
    enabled(c)
    if not isinstance(hooks,GroupImportHooks)or not hooks.prepared:raise ValueError('Prepared declared import file required')
    files=[BrowserUploadFile(path=hooks.asset,sha256=c['group_import']['asset_sha256'],description='Native group metadata export supplied by this task; no projects or repositories.')]
    upload_file_metadata(files);return files


def fields(c):enabled(c);return []
def public_goal(c):enabled(c);return c['goal']
def feedback(result):return rule.feedback(result)
