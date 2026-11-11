"""Shared terminal-only persisted GitLab goals with private native protection.

Public declarations are versioned training derivatives. No hook navigates,
chooses a control, suggests a next action, or evaluates an intermediate step.
The ordinary runner requires a completed normal handoff proof before inference.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from .source_revision_binding import binding,fingerprint,require_source_binding
from .gitlab_native_read_runtime import full_snapshot
from .gitlab_mutation_native import repository,database,protection,protection_equal
from .gitlab_persisted_mutation import evaluate
from .site_navigation_rules import valid_initial_page
from .browser_assets import BrowserUploadFile,upload_file_metadata
from .io_utils import atomic_write_json

VERSION='gitlab-persisted-normal-runtime-v1'
PROOF_VERSION='gitlab-persisted-normal-controls-v1'
AUTHORIZED_TARGET_WRITES=True
KINDS={'repository_file','notifications','visibility'}
SHA=re.compile('[0-9a-f]{64}')


def enabled(c):
    if 'gitlab_persisted_goal' not in c:return False
    s=c['gitlab_persisted_goal']
    if (c.get('domain')!='gitlab' or not isinstance(s,dict) or s.get('version')!=VERSION
            or s.get('kind') not in KINDS or c.get('completion')!={'family':'gitlab_persisted_goal'}
            or c.get('eligible_for_training') is not False or c.get('heldout_quarantine') is not False
            or c.get('is_explicit_derivative') is not True or c.get('original_benchmark_equivalence') is not False
            or not isinstance(s.get('declaration'),dict) or s['declaration'].get('kind')!=s['kind']
            or any(c.get(k) for k in ('query','gitlab_native_read','gitlab_grouped_goal','preferences','clipboard','repository_download','ref_creation'))):
        raise ValueError('Explicit mapped deterministic persisted GitLab goal required')
    binding(c);return True


def require_original_binding(c,original,inventory):
    enabled(c);return require_source_binding(c,original,inventory,domain='gitlab')


def require_native_controls(c,p):
    enabled(c)
    if (not isinstance(p,dict) or p.get('version')!='gitlab-persisted-native-controls-v1'
            or p.get('source_task_id')!=c['source_task_id'] or not SHA.fullmatch(p.get('archive_sha256',''))
            or p.get('actor_attempts')!=0 or p.get('api_calls')!=0):
        raise ValueError('Measured private two-cold native controls required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list) or len(cycles)!=2:raise ValueError('Two independent native cycles required')
    for row in cycles:
        if (row.get('passed_native_controls') is not True or not isinstance(row.get('checks'),dict)
                or not row['checks'] or not all(v is True for v in row['checks'].values())
                or row.get('native_spec',{}).get('kind')!=c['gitlab_persisted_goal']['kind']):
            raise ValueError('Actual complete native control receipt required')
        spec=row['native_spec'];old=row['initial'];new=row['final']
        if evaluate(spec,old,old,protected_state_unchanged=True)['status']!='failure':raise ValueError('Original unsatisfied precondition required')
        account_id=int(spec['identity'].split(':')[-1]) if spec['kind']=='notifications' else None
        # Full table shape is retained even when exact visibility relations are additional.
        for name in ('initial_guard','final_guard'):
            full_snapshot({k:v for k,v in row[name].items() if k!='visibility_relation'})
        if not protection_equal(row['initial_guard'],row['final_guard'],spec,account_id):raise ValueError('Declared native authorization guard did not pass')
        if evaluate(spec,old,new,protected_state_unchanged=True)['status']!='success':raise ValueError('Native persisted positive missing')
    for name in ('native_spec','initial','initial_guard'):
        if cycles[0][name]!=cycles[1][name]:raise ValueError('Independent native reset differs: '+name)
    return deepcopy(cycles[0])


REF_CAPTURE=r'''require 'json';require 'open3'
root='/var/opt/gitlab/git-data/repositories';git='/opt/gitlab/embedded/bin/git'
rows={}
Dir.glob(root+'/**/*.git').sort.each do |path|
 raise 'symlink repository' if File.symlink?(path)
 next unless File.directory?(path)
 relative=path.delete_prefix(root+'/')
 # Gitaly's cache invalidation state mirrors repository names but is not a
 # bare Git repository. Preserve all actual project/wiki/pool repositories.
 if relative.start_with?('+gitaly/state/')
  raise 'unknown Gitaly state identity' unless relative.match?(%r{\A\+gitaly/state/(?:@hashed|@pools)/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}(?:\.wiki)?\.git\z})
  raise 'repository hidden in Gitaly state' if File.exist?(path+'/HEAD') || File.exist?(path+'/objects') || File.exist?(path+'/refs')
  raise 'symlink Gitaly state member' if Dir.glob(path+'/**/*',File::FNM_DOTMATCH).any?{|x|File.symlink?(x)}
  next
 end
 run=lambda do |*args|
  stdout,stderr,status=Open3.capture3(git,'--git-dir='+path,*args)
  raise ['native git failed',relative,args.join(' '),status.exitstatus,stderr.strip].join(' | ') unless status.success?
  stdout
 end
 raise 'non-bare repository' unless run.call('rev-parse','--is-bare-repository').strip=='true'
 refs={};run.call('for-each-ref','--format=%(refname) %(objectname)').each_line do |line|
  name,oid=line.strip.split(' ',2);raise 'duplicate ref' if refs.key?(name);refs[name]=oid
 end
 symbolic,_,symbol_status=Open3.capture3(git,'--git-dir='+path,'symbolic-ref','-q','HEAD')
 head,_,head_status=Open3.capture3(git,'--git-dir='+path,'rev-parse','--verify','HEAD')
 rows[relative]={'head'=>head_status.success? ? head.strip : nil,'symbolic_head'=>symbol_status.success? ? symbolic.strip : nil,'refs'=>refs}
end
raise 'empty repository discovery' if rows.empty?
puts JSON.generate({'version'=>'gitlab-all-native-refs-v1','complete'=>true,'repositories'=>rows})
'''


def validate_refs(value):
    if (not isinstance(value,dict) or set(value)!={'version','complete','repositories'}
            or value['version']!='gitlab-all-native-refs-v1' or value['complete'] is not True
            or not isinstance(value['repositories'],dict) or not value['repositories']):raise ValueError('Complete native repository discovery required')
    for path,row in value['repositories'].items():
        if (not isinstance(path,str) or path.startswith('/') or '..' in path.split('/') or not path.endswith('.git')
                or not isinstance(row,dict) or set(row)!={'head','symbolic_head','refs'} or not isinstance(row['refs'],dict)):
            raise ValueError('Malformed native repository identity')
        for oid in [row['head'],*row['refs'].values()]:
            if oid is not None and not re.fullmatch('[0-9a-f]{40,64}',oid):raise ValueError('Native object identity missing')
        if row['symbolic_head'] is not None and not row['symbolic_head'].startswith('refs/heads/'):raise ValueError('Malformed native HEAD')
    return value


def refs_snapshot(site):
    return validate_refs(json.loads(site.command(['/opt/gitlab/embedded/bin/ruby','-e',REF_CAPTURE],capture_output=True,text=True,timeout=90).stdout))


def target_repository(spec):
    digest=hashlib.sha256(str(spec['identity']).encode()).hexdigest()
    return '@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'


def refs_equal(before,after,spec,initial,final):
    validate_refs(before);validate_refs(after)
    old=before['repositories'];new=after['repositories']
    if set(old)!=set(new):return False
    if spec['kind']!='repository_file':return before==after
    target=target_repository(spec)
    if target not in old:return False
    if {k:v for k,v in old.items() if k!=target}!={k:v for k,v in new.items() if k!=target}:return False
    a,b=old[target],new[target];branch='refs/heads/'+spec['branch']
    if a['head']!=initial['head'] or b['head']!=final['head'] or a['symbolic_head']!=branch or b['symbolic_head']!=branch:return False
    previous={k:v for k,v in a['refs'].items() if k!=branch};current={k:v for k,v in b['refs'].items() if k!=branch}
    if any(current.get(k)!=v for k,v in previous.items()):return False
    # GitLab's exact native retention pointer may be created for the submitted commit.
    for name,oid in current.items():
        if name in previous:continue
        if name!='refs/keep-around/'+oid or oid not in (initial['head'],final['head']):return False
    return a['refs'].get(branch)==initial['head'] and b['refs'].get(branch)==final['head']


def protection_integrity(before,after,spec,account_id):
    # An unchanged unsatisfied state is a valid negative control, not a guard failure.
    return before==after or protection_equal(before,after,spec,account_id)


def require_admission(c,p):
    from .archived_admission_proof import resolve
    p=resolve(c,p)
    base=require_native_controls(c,p.get('native_controls',{}))
    if (p.get('version')!=PROOF_VERSION or p.get('contract_fingerprint')!=fingerprint(c)
            or p.get('original_binding')!=binding(c) or p.get('actor_attempts')!=0 or p.get('api_calls')!=0
            or p.get('formal_preinference_lifecycle_verified') is not True):raise ValueError('Completed normal persisted lifecycle proof required')
    cycles=p.get('cycles')
    if not isinstance(cycles,list) or len(cycles)!=2:raise ValueError('Two fresh normal deployments required')
    ids=[r.get('fresh_instance_id') for r in cycles]
    if any(not SHA.fullmatch(x or '') for x in ids) or ids[0]==ids[1]:raise ValueError('Independent fresh instances required')
    names={'no_op','positive'} | ({'unsaved'} if base['native_spec']['kind']!='notifications' else set())
    for cycle in cycles:
        if cycle.get('native_spec')!=base['native_spec'] or cycle.get('initial')!=base['initial']:raise ValueError('Native initial source object differs')
        full_snapshot({k:v for k,v in cycle['initial_guard'].items() if k!='visibility_relation'});validate_refs(cycle['initial_refs'])
        if set(cycle.get('controls',{}))!=names:raise ValueError('All normal terminal negative/positive controls required')
        for name,r in cycle['controls'].items():
            if (r.get('initial_start_preserved') is not True or r.get('private_feedback_clean') is not True
                    or r.get('terminal_integrity') is not True or r.get('normal_lifecycle_verified') is not True
                    or r.get('initial')!=cycle['initial'] or r.get('initial_guard')!=cycle['initial_guard']
                    or r.get('initial_refs')!=cycle['initial_refs']):raise ValueError('Exact actual common runner lifecycle/initial guard required')
            guard=protection_integrity(r['initial_guard'],r['final_guard'],base['native_spec'],r['account_id'])
            guard=guard and refs_equal(r['initial_refs'],r['final_refs'],base['native_spec'],r['initial'],r['final'])
            result=evaluate(base['native_spec'],r['initial'],r['final'],protected_state_unchanged=guard)
            if not valid_initial_page(r['page'],site_origin=r['site_origin']):raise ValueError('Valid terminal document required')
            if result['status']!=('success' if name=='positive' else 'failure'):raise ValueError('Actual normal terminal result differs')
            if r['judgment'].get('status')!=result['status']:raise ValueError('Recorded terminal judge differs from native evidence')
            if base['native_spec']['kind']=='repository_file' and c['gitlab_persisted_goal']['declaration']['ui']=='upload' and name=='positive':
                if r.get('declared_upload_used') is not True:raise ValueError('Common declared-file upload action handoff required')
    for key in ('native_spec','initial','initial_guard','initial_refs'):
        if cycles[0][key]!=cycles[1][key]:raise ValueError('Two fresh normal native baselines differ: '+key)
    return deepcopy(cycles[0])


class PersistedGoalHooks:
    def __init__(self,c,p,directory):
        self.contract=deepcopy(c);self.proof=deepcopy(p);self.directory=Path(directory)
        from .archived_admission_proof import resolve
        original=resolve(c,p)
        self.base=require_native_controls(c,original.get('native_controls',original));self.context=None;self.initial_page=None;self.events=[];self.scored=False;self.prepared=False
        self.reader_context=None;self.closed=False;self.terminal_native=None
    def prepare(self,site,username):
        if self.prepared or self.closed:raise ValueError('One bound source reset required')
        self.site=site;self.generation=site.generation
        try:self._prepare(site,username)
        except BaseException:
            self.close();raise
    def _prepare(self,site,username):
        from lab_generate_skill.site_database import select_rows
        from probe_gitlab_mutation_batch import configure,read
        rows=select_rows(site,"SELECT id FROM users WHERE username='"+username.replace("'","''")+"'")
        if len(rows)!=1:raise ValueError('Unique bound native account required')
        # Same native cache initialization for the private probe and common runner.
        key=('persisted_native',getattr(site,'generation',0))
        if getattr(site,'_persisted_native_generation',None)!=key:
            import gitlab_native_wiki_cache_init as wiki;import gitlab_native_issue_cache_init as issue
            wiki.initialize(site,self.directory/'wiki-cache-initialization');issue.initialize(site,self.directory/'issue-cache-initialization')
            site._persisted_native_generation=key
        if self.contract['gitlab_persisted_goal']['kind']=='visibility':
            from .gitlab_visibility_session import bind_visibility_reader
            context=bind_visibility_reader(site,self.directory/'native-reader')
            context.__enter__();self.reader_context=context
        self.account_id=rows[0]['id'];declaration=self.contract['gitlab_persisted_goal']['declaration']
        case={'spec':declaration};self.spec,contents=configure(site,case,self.account_id)
        self.initial=read(site,self.spec)
        if self.spec!=self.base['native_spec'] or self.initial!=self.base['initial']:raise ValueError('Actual normal native reset differs from two-cold controls')
        self.before=protection(site,self.spec,self.account_id,self.directory/'initial-protection-progress.jsonl');self.refs_before=refs_snapshot(site)
        from .archived_admission_proof import VERSION as ARCHIVED_PROOF_VERSION
        if self.proof.get('version')==PROOF_VERSION or self.proof.get('storage_format')==ARCHIVED_PROOF_VERSION:
            expected=require_admission(self.contract,self.proof)
            if self.before!=expected['initial_guard'] or self.refs_before!=expected['initial_refs']:raise ValueError('Whole normal private reset differs from admitted proof')
        self.uploads=[]
        if declaration.get('ui')=='upload':
            asset=self.directory/'task-files'/Path(declaration['path']).name;asset.parent.mkdir(parents=True,exist_ok=False);asset.write_bytes(contents)
            self.uploads=[BrowserUploadFile(path=str(asset.resolve()),sha256=hashlib.sha256(contents).hexdigest(),description='File supplied by this task; preserve its filename and bytes.')]
            upload_file_metadata(self.uploads)
        self.site=site;self.prepared=True;self.events.append('prepare')
        self._persist_capture({'final':None,'guard':None,'refs':None,'errors':[]},
                              stage='initial_verified')
    def attach(self,context):
        if not self.prepared or self.context is not None:raise ValueError('One prepared normal browser context required')
        self.context=context;self.events.append('attach')
    def observe_initial(self,page):
        if self.initial_page is not None or page.context is not self.context:raise ValueError('One bound normal initial page required')
        if page.url!=self.site.url+self.contract['start_path']:raise ValueError('Actual source first start differs')
        self.initial_page=page;self.events.append('observe_initial')
    def record(self,page):
        if page.context is not self.context or self.initial_page is None:raise ValueError('Bound normal observation required')
        self.events.append('record')
    def capture_terminal(self,page,terminal):
        if page.context is not self.context or self.initial_page is None:raise ValueError('Bound normal terminal page required')
        if self.contract['gitlab_persisted_goal']['kind']=='visibility':
            if self.closed or self.terminal_native is not None:raise ValueError('One live native terminal capture required')
            # Session.close captures the terminal page and then releases hooks;
            # scoring happens afterwards. Read the real terminal state now, while
            # the attempt-owned Rails process is still alive. No intermediate score.
            self.terminal_native=self._read_terminal(self.site)
        self.events.append('capture_terminal');terminal['gitlab_persisted_goal_terminal']={'captured_after_termination':True}
    def _read_terminal(self,site):
        if site is not self.site or site.generation!=self.generation:
            raise ValueError('Native terminal capture cannot cross website reset')
        state={'final':None,'guard':None,'refs':None,'errors':[]}
        try:
            from probe_gitlab_mutation_batch import read
            state['final']=read(site,self.spec,self.initial)
            self._persist_capture(state,stage='terminal_target_read')
            state['guard']=protection(site,self.spec,self.account_id,self.directory/'final-protection-progress.jsonl')
            self._persist_capture(state,stage='terminal_guard_read')
            state['refs']=refs_snapshot(site)
        except Exception as error:state['errors'].append({'exception_type':type(error).__name__})
        self._persist_capture(state,stage='terminal_read_complete' if not state['errors'] else 'terminal_read_failed')
        return state
    def _persist_capture(self,state,*,stage,integrity=None):
        # One private, atomically replaced file; no growing snapshot series.
        # A watchdog interruption may retain partial evidence, but it must not
        # imply a score or permit skipped integrity checks on the next reset.
        atomic_write_json(self.directory/'private-persisted-protection.json',{
            'initial':self.initial,'final':state['final'],'initial_guard':self.before,
            'final_guard':state['guard'],'initial_refs':self.refs_before,
            'final_refs':state['refs'],'native_spec':self.spec,'account_id':self.account_id,
            'integrity':integrity,'capture_errors':state['errors'],
            'capture_stage':stage,'terminal_score_completed':stage=='scored'})
    def score_terminal(self,site,page,*,runtime_error=None):
        if not self.prepared or self.scored or site is not self.site or site.generation!=self.generation:raise ValueError('One terminal judgment on the same reset required')
        self.scored=True
        if self.contract['gitlab_persisted_goal']['kind']=='visibility':
            state=self.terminal_native or {'final':None,'guard':None,'refs':None,'errors':[{'exception_type':'MissingNativeTerminalCapture'}]}
        else:state=self._read_terminal(site)
        self.final=state['final'];self.after=state['guard'];self.refs_after=state['refs'];errors=state['errors']
        integrity=not errors and protection_integrity(self.before,self.after,self.spec,self.account_id) and refs_equal(self.refs_before,self.refs_after,self.spec,self.initial,self.final)
        result=evaluate(self.spec,self.initial,self.final,protected_state_unchanged=bool(integrity),runtime_error=runtime_error or bool(errors))
        if result['status']!='unknown' and not valid_initial_page(page,site_origin=site.url):result.update(status='failure',reward=0.0)
        self._persist_capture(state,stage='scored',integrity=bool(integrity))
        result['version']=VERSION;self.events.append('score_terminal')
        atomic_write_json(self.directory/'normal-hook-events.json',self.events)
        return result,integrity
    def close(self):
        if self.closed:return
        self.closed=True
        if self.reader_context is not None:
            context=self.reader_context;self.reader_context=None
            context.__exit__(None,None,None)


def upload_files(contract,hooks):
    if not enabled(contract):return []
    if not isinstance(hooks,PersistedGoalHooks) or not hooks.prepared:raise ValueError('Prepared declared task resources required')
    return list(hooks.uploads)


def feedback(result):
    return {'status':result.get('status'),'checks':[{'condition':k,'passed':v} for k,v in result.get('checks',{}).items()]}
