"""One explicit, evidence-bound continuation of an unstarted model inference.

This module cannot retry a model failure or change a task/proof. A complete old
archive, its frozen producer and a terminal scheduler attestation must prove an
initializer failed before the first model load. The old first claim stays in
place; the sole continuation has a separate lease and output archive.
"""
import ast,hashlib,json,os,re,tarfile
from pathlib import Path,PurePosixPath
from copy import deepcopy
from .io_utils import atomic_write_json
VERSION='native-initializer-zero-inference-continuation-v1'
MISSING_ASSET='scripts/gitlab_native_wiki_cache_init.rb'
SOURCES=('2b189826938239798f93','2dde6194b86bf76d25b9','2e6315cc8d029eb9e78a','6addb348032f05c09678','7e1ecbfe83910a7f3ae7','9da3e5f38722764ba141','b6b1755abdbf3d7b075e')
SOURCE_FILES=('attempt-started.json','result.json','native-read-initialization/columns-before-native-initialization.json',
    'native-read-initialization/columns-after-native-initialization.json','native-read-initialization/native-cache-initialization-capture.json',
    'native-read-initialization/native-cache-initialization-column-difference.json','native-read-initialization/protected-before-native-initialization-progress.jsonl',
    'native-read-initialization/protected-before-progress.jsonl')
MARKER=re.compile(r'^(generation-|partial-generation|actor-input|actor-budget|actor-protocol|rollout|trajectory|step-|model-loaded|inference-started)')
SHA=re.compile(r'[0-9a-f]{64}')


def regular_bytes(path):
    path=Path(path)
    if not path.is_absolute()or path.is_symlink()or not path.is_file():raise ValueError('Regular absolute unchanged continuation input required')
    for parent in path.parents:
        if parent.is_symlink():raise ValueError('Continuation input parent symlink forbidden')
    return path.read_bytes()


def digest(path):return hashlib.sha256(regular_bytes(path)).hexdigest()


def pinned(path,value):
    if not isinstance(value,str)or not SHA.fullmatch(value)or digest(path)!=value:raise ValueError('Continuation origin hash drift')
    return regular_bytes(path)


def archive_bytes(archive,sha,manifest=None,manifest_sha=None):
    pinned(archive,sha);rows=json.loads(pinned(manifest,manifest_sha))['members']if manifest else None
    selected={};total=0
    with tarfile.open(archive,'r:gz')as t:
        for m in t:
            p=PurePosixPath(m.name)
            if not m.isfile()or (manifest is not None and m.mode!=0o600)or p.is_absolute()or '..'in p.parts or '\\'in m.name or m.name in selected:raise ValueError('Unique safe regular actual continuation archive required')
            total+=m.size
            if m.size>160*1024**2 or total>2*1024**3:raise ValueError('Bounded complete continuation evidence required')
            data=t.extractfile(m).read(m.size+1)
            if len(data)!=m.size:raise ValueError('Actual archive member size differs')
            if rows is not None:
                row=rows.get(m.name)
                if not isinstance(row,dict)or row.get('bytes')!=m.size or row.get('sha256')!=hashlib.sha256(data).hexdigest():raise ValueError('Complete raw continuation archive bytes differ')
            selected[m.name]=data
    if not selected or rows is not None and set(selected)!=set(rows):raise ValueError('Complete raw member coverage differs')
    return selected


def failure_before_model_load(raw,code,task,job):
    names={name for name in raw if PurePosixPath(name).parts[0]==task}
    if names!={task+'/'+n for n in SOURCE_FILES}:raise ValueError('Complete closed pre-inference source artifacts required')
    for name in raw:
        if MARKER.match(PurePosixPath(name).name):raise ValueError('Any inference/input/step/rollout marker prevents continuation')
    claim=json.loads(raw[task+'/attempt-started.json']);result=json.loads(raw[task+'/result.json'])
    if claim!={'job':job,'task':task,'scripted':False}:raise ValueError('Actual original source first-attempt claim differs')
    if result.get('task_id')!=task or result.get('status')!='runtime_or_contract_error'or result.get('rollout_saved')is not False or result.get('api_calls')!=0 or result.get('evaluation')!={'status':'unknown','reward':None}:raise ValueError('Only a closed native initializer failure may continue')
    diagnostic=result.get('diagnostic',{});frames=diagnostic.get('frames',[])
    if diagnostic.get('type')!='FileNotFoundError'or diagnostic.get('stage')!='site_navigation_attempt':raise ValueError('Exact native asset initialization exception required')
    expected=[('run_site_navigation_once.py','main'),('gitlab_native_read_runtime.py','prepare'),('gitlab_native_wiki_cache_init.py','initialize'),('gitlab_native_wiki_cache_init.py','initialize'),('gitlab_native_wiki_cache_init.py','invoke'),('pathlib.py','read_bytes'),('pathlib.py','open')]
    if [(f.get('file'),f.get('function'))for f in frames]!=expected:raise ValueError('Exact pre-model missing native asset stack required')
    if MISSING_ASSET in code:raise ValueError('The declared missing asset actually exists in the old frozen runtime')
    tree=ast.parse(code['scripts/run_site_navigation_once.py'])
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
    calls=[n for n in ast.walk(main)if isinstance(n,ast.Call)]
    pre=[n.lineno for n in calls if isinstance(n.func,ast.Attribute)and isinstance(n.func.value,ast.Name)and n.func.value.id=='native_read_hooks'and n.func.attr=='prepare']
    loads=[n.lineno for n in calls if(isinstance(n.func,ast.Name)and n.func.id=='load_backend')or(isinstance(n.func,ast.Attribute)and isinstance(n.func.value,ast.Name)and n.func.value.id=='backend_holder'and n.func.attr=='acquire')]
    if len(pre)!=1 or not loads or frames[0].get('line')!=pre[0]or pre[0]>=min(loads):raise ValueError('Frozen actual initializer must precede every model load path')
    native=code['scripts/gitlab_native_wiki_cache_init.py'].decode()
    invoke=next(n for n in ast.parse(native).body if isinstance(n,ast.FunctionDef)and n.name=='invoke')
    asset_reads=[n.lineno for n in ast.walk(invoke)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='read_bytes']
    if not asset_reads or frames[4].get('line')!=min(asset_reads)or "script=Path(__file__).with_suffix('.rb')"not in native:raise ValueError('Actual missing-file frame must read the frozen native Ruby asset')
    capture=json.loads(raw[task+'/native-read-initialization/native-cache-initialization-capture.json'])
    if capture.get('primary_exception_type')!='FileNotFoundError'or capture.get('capture_errors')!=[]or capture.get('full_before')!=capture.get('full_after')or capture.get('native_record_complete')is not False or capture.get('actor_attempts')!=0 or capture.get('api_calls')!=0:raise ValueError('Full native pre-model failure capture must be unchanged')
    from .gitlab_native_read_runtime import full_snapshot
    full_snapshot(capture['full_before'])
    before=json.loads(raw[task+'/native-read-initialization/columns-before-native-initialization.json']);after=json.loads(raw[task+'/native-read-initialization/columns-after-native-initialization.json'])
    from gitlab_project_column_hashes import validate,difference
    validate(before);validate(after)
    if before!=after or json.loads(raw[task+'/native-read-initialization/native-cache-initialization-column-difference.json'])!=difference(before,after):raise ValueError('All original native project columns must be unchanged')
    return claim


class InitializationContinuation:
    """Opaque validated provenance; not an actor-visible retry flag."""
    def __init__(self,spec,*,terminal_query):
        self.spec=deepcopy(spec);self.terminal_query=terminal_query;self.ready=False;self.started=[];self.lease=None;self.verify_origin();self.ready=True
    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('sources')!=list(SOURCES)or s.get('continuation_id')!='initialization-continuation-1'or s.get('api_calls')!=0 or s.get('old_model_generations')!=0:raise ValueError('Only explicit reviewed GitLab7 zero-inference initialization continuation')
        wave=Path(s['wave']).resolve();bundle=Path(s['old_bundle']).resolve()
        if wave.parent!=Path(s['base']).resolve()or bundle.parent!=wave.parent/'actor-bundles'or s['new_shared_out']!=str(wave/'actor/initialization-continuation-1'):raise ValueError('Same original wave/claim with unique continuation output required')
        rows={name:json.loads(pinned(pin['path'],pin['sha256']))for name,pin in s['metadata_pins'].items()}
        required={'submitted','original_claim','old_bundle_plan','old_bundle_claims','old_worker_state','old_local_output_state','raw_manifest','raw_receipt'}
        if set(rows)!=required:raise ValueError('Complete actual original claim/submission/closure metadata required')
        expected_paths={'submitted':wave/'submitted.json','original_claim':wave/'first-actor-claim/preflight.json',
            'old_bundle_plan':bundle/'plan.json','old_bundle_claims':bundle/'claimed-waves.json',
            'old_worker_state':bundle/'worker-state.json','old_local_output_state':bundle/'local-output-state.json',
            'raw_manifest':wave/'actor/0/diagnostic-members.json','raw_receipt':wave/'actor/0/actor-archive-receipt.json'}
        if any(Path(s['metadata_pins'][name]['path']).resolve()!=path for name,path in expected_paths.items()):raise ValueError('Actual original producer metadata locations required')
        submitted,claim,plan=(rows[n]for n in('submitted','original_claim','old_bundle_plan'))
        job=submitted['job_id'];states=self.terminal_query(job)
        command=submitted.get('command')
        if not isinstance(command,list)or len(command)!=7 or command[:2]!=['sbatch','--parsable']or command[3:5]!=[s['old_runtime_archive'],s['old_runtime_sha256']]or command[5:]!=[str(bundle),s['metadata_pins']['old_bundle_plan']['sha256']]:raise ValueError('Actual original scheduler invocation required')
        pinned(command[2],submitted['worker_sha256'])
        if not isinstance(states,dict)or states!={job:'COMPLETED'}:raise ValueError('Exact old allocation must be authoritatively terminal COMPLETED')
        if submitted.get('frozen_code_sha256')!=s['old_runtime_sha256']or submitted.get('bundle_plan_sha256')!=s['metadata_pins']['old_bundle_plan']['sha256']or submitted.get('sources')!=7:raise ValueError('Actual old frozen packet and original bundle must match submission')
        if len(plan.get('waves',[]))!=1 or plan['waves'][0]!=claim or rows['old_bundle_claims']!=[claim]or plan.get('tasks')!=7 or plan.get('domain')!='gitlab':raise ValueError('Retained original first-claim provenance differs')
        if claim['wave']!=str(wave)or claim['manifest']!=str(wave/'admitted-tasks.jsonl')or claim.get('tasks')!=7 or claim.get('api_calls')!=0:raise ValueError('Original unchanged seven-source first claim required')
        if digest(claim['manifest'])!=claim['manifest_sha256']or digest(wave/'contracts.jsonl')!=claim['contracts_sha256']or digest(wave.parent/'inventory.jsonl')!=claim['inventory_sha256']:raise ValueError('Original manifest/contract/inventory drift')
        self.contracts=list(map(json.loads,regular_bytes(claim['manifest']).decode().splitlines()))
        current_project=wave.parent.parent.parent/'TFcode-generate-skill/Lab_generate_skill'
        if Path(s['current_runtime_project']).resolve()!=current_project.resolve():raise ValueError('Current canonical runtime source policy required')
        from build_map_osm_export_capability import active_scope
        if Path(active_scope(current_project)['scope_manifest']).resolve()!=Path(s['source_policy_pin']['path']).resolve():raise ValueError('Current source policy pointer changed')
        policy=json.loads(pinned(s['source_policy_pin']['path'],s['source_policy_pin']['sha256']))
        from prepare_admitted_site_actor import inventory_aliases
        inventory=list(map(json.loads,regular_bytes(wave.parent/'inventory.jsonl').decode().splitlines()))
        aliases=inventory_aliases(inventory);excluded=set(policy['external_excluded_task_ids'])|set(policy['heldout_overlap_quarantined_task_ids'])
        if any(aliases[source]&excluded for source in SOURCES):raise ValueError('Current original-source external/heldout alias exclusion prevents continuation')
        if [c['task_id']for c in self.contracts]!=list(SOURCES)or any(c.get('source_task_id',c['task_id'])!=c['task_id']for c in self.contracts):raise ValueError('Exact original source list required')
        if [r['source_task_id']for r in claim['proofs']]!=list(SOURCES):raise ValueError('Original proof source identity differs')
        for proof in claim['proofs']:
            if digest(proof['file'])!=proof['sha256']:raise ValueError('Admitted original proof drift')
        state=rows['old_worker_state']
        if state.get('status')!='completed'or state.get('api_calls')!=0 or state.get('completed_waves')!=[{'wave':str(wave),'tasks':7,'result_records':7}]:raise ValueError('Old ordinary worker must have closed all seven initializer failures')
        local=rows['old_local_output_state']
        if local.get('bundle')!=str(bundle)or local.get('plan_sha256')!=submitted['bundle_plan_sha256']or set(local.get('waves',{}))!={str(wave)}or local['waves'][str(wave)].get('status')!='runner_closed':raise ValueError('Actual archived old worker closure required')
        code=archive_bytes(s['old_runtime_archive'],s['old_runtime_sha256'])
        raw=archive_bytes(s['raw_archive'],s['raw_archive_sha256'],s['metadata_pins']['raw_manifest']['path'],s['metadata_pins']['raw_manifest']['sha256'])
        manifest=rows['raw_manifest'];receipt=rows['raw_receipt']
        if len(raw)!=117 or manifest.get('archive_sha256')!=s['raw_archive_sha256']or manifest.get('member_count')!=117 or manifest.get('archival_status')!='complete_member_archive_saved'or receipt.get('archive_sha256')!=s['raw_archive_sha256']or receipt.get('member_count')!=117 or receipt.get('full_output_not_sampled')is not True:raise ValueError('Exact original117 closed raw members required')
        self.old_claim_bytes={};self.allowed_old_artifacts={}
        for task in SOURCES:
            failure_before_model_load(raw,code,task,job);self.old_claim_bytes[task]=raw[task+'/attempt-started.json']
            result=wave/'actor/0'/task/'result.json';marker=wave/'actor/0'/task/'attempt-archive.json'
            if regular_bytes(result)!=raw[task+'/result.json']:raise ValueError('Retained result changed from complete raw archive')
            value=json.loads(regular_bytes(marker))
            if value.get('archive_sha256')!=s['raw_archive_sha256']or value.get('first_completed_generation_member')is not None or value.get('raw_member_count')!=8 or value.get('automatic_retry')is not False:raise ValueError('Retained actual attempt archive marker differs')
            for p in (result,marker):self.allowed_old_artifacts[p.resolve()]=digest(p)
        for name,pin in s['retained_marker_pins'].items():
            pinned(pin['path'],pin['sha256'])
            if Path(pin['path']).resolve()not in self.allowed_old_artifacts:raise ValueError('Only exact retained zero-inference original artifacts may be permitted')
        if {Path(p['path']).resolve()for p in s['retained_marker_pins'].values()}!=set(self.allowed_old_artifacts):raise ValueError('All exact retained old result/archive markers must stay pinned')
        for directory in (wave/'first-actor-claim/worker-started',bundle/'worker-started'):
            if directory.is_symlink()or not directory.is_dir()or any(directory.iterdir()):raise ValueError('Retained original worker-started claim must be unchanged')
        self.wave,self.bundle,self.claim,self.raw,self.code,self.old_job=wave,bundle,claim,raw,code,job
        return claim
    def require_guard_binding(self,base,wave,selected):
        if not self.ready or Path(base).resolve()!=self.wave.parent or Path(wave).resolve()!=self.wave or list(selected)!=self.contracts:raise ValueError('Initialization continuation cannot exempt another wave or changed selected sources')
        self.verify_origin()
    def permits_existing_artifact(self,file):
        original=Path(file).absolute();p=original.resolve();expected=self.allowed_old_artifacts.get(p)
        if expected is None:return False
        if digest(original)!=expected:raise ValueError('Retained zero-inference original artifact drift')
        return True
    def validate_current_admission(self):
        self.verify_origin()
        from prepare_admitted_site_actor import prepare
        actual=prepare(self.wave,self.claim['manifest'],self.claim['domain'],self.claim['control_job'],initialization_continuation=self)
        stable=lambda x:{k:v for k,v in x.items()if k!='control_states'}
        if stable(actual)!=stable(self.claim):raise ValueError('Current normal source/alias/exclusion/proof guard differs from original first claim')
        return actual
    def start(self,bundle,local_out,*,manifest_path):
        """Root-reviewed dedicated launcher calls once, after real asset preflight."""
        self.validate_current_admission();bundle=Path(bundle).resolve();local_out=Path(local_out).resolve()
        current_job=os.environ.get('SLURM_JOB_ID')
        if not isinstance(current_job,str)or not re.fullmatch(r'[1-9][0-9]*',current_job)or current_job==self.old_job:raise ValueError('A new actual allocation must own the one initialization continuation')
        if bundle.parent!=self.wave.parent/'actor-bundles'or bundle==self.bundle or bundle.exists():raise ValueError('New unique initialization continuation bundle required')
        from .native_runtime_assets import preflight
        report=preflight(Path(__file__).resolve().parents[2],self.contracts,manifest_path=manifest_path)
        bundle.mkdir(mode=0o700)
        # One exclusive lease within the old first claim; no second first claim.
        lease=self.wave/'first-actor-claim'/'initialization-continuation-1';lease.mkdir(mode=0o700)
        record={'version':VERSION,'old_job':self.old_job,'old_first_claim_sha256':self.spec['metadata_pins']['original_claim']['sha256'],
            'spec_sha256':hashlib.sha256(json.dumps(self.spec,sort_keys=True).encode()).hexdigest(),
            'bundle':str(bundle),'local_out':str(local_out),'shared_out':self.spec['new_shared_out'],
            'job':os.environ.get('SLURM_JOB_ID'),'pid':os.getpid(),'sources':list(SOURCES),'first_model_inference_continues_existing_claim':True,'automatic_retry':False}
        atomic_write_json(lease/'lease.json',record);atomic_write_json(bundle/'plan.json',{'version':VERSION,'spec':self.spec,'lease':record,'assets':report})
        self.lease,self.local_out=lease,local_out;self.lease_digest=digest(lease/'lease.json');return record
    def validate_runner_selection(self,manifest,out,rows):
        if self.lease is None or digest(self.lease/'lease.json')!=self.lease_digest or Path(out).resolve()!=self.local_out or Path(manifest).resolve()!=Path(self.claim['manifest']).resolve()or list(rows)!=self.contracts:raise ValueError('Only the owned exact initialization continuation may enter the normal runner')
        self.verify_origin()
    def begin_source(self,contract,directory):
        task=contract.get('task_id');directory=Path(directory).resolve()
        if self.lease is not None:
            record=json.loads(regular_bytes(self.lease/'lease.json'))
            if digest(self.lease/'lease.json')!=self.lease_digest or record.get('pid')!=os.getpid()or record.get('job')!=os.environ.get('SLURM_JOB_ID'):raise ValueError('Only the exact lease-owning live worker may continue initialization')
        if self.lease is None or task not in SOURCES or directory!=self.local_out/task or task in self.started or self.contracts[len(self.started)]!=contract:raise ValueError('One ordered existing-first-claim continuation per source')
        self.verify_origin()
        if any(directory.iterdir()):raise ValueError('Never replace current inference or source outputs')
        with(directory/'attempt-started.json').open('xb')as file:file.write(self.old_claim_bytes[task])
        atomic_write_json(directory/'initialization-continuation.json',{'version':VERSION,'old_first_claim_sha256':self.spec['metadata_pins']['original_claim']['sha256'],
            'old_attempt_claim_sha256':hashlib.sha256(self.old_claim_bytes[task]).hexdigest(),'lease':str(self.lease),'lease_sha256':self.lease_digest,
            'source_task_id':task,'current_job':os.environ.get('SLURM_JOB_ID'),'old_job':self.old_job,'first_model_generation':True,'actor_failure_retry':False})
        self.started.append(task)


def require_guard_authority(authority,base,wave,selected):
    from .surface_png_continuation import SurfacePngContinuation
    if type(authority) is SurfacePngContinuation:
        authority.require_guard_binding(base,wave,selected)
        return
    from .surface_path_continuation import SurfacePathContinuation
    if type(authority) is SurfacePathContinuation:
        authority.require_guard_binding(base,wave,selected)
        return
    from .terminal_capture_continuation import TerminalCaptureContinuation
    if type(authority) is TerminalCaptureContinuation:
        authority.require_guard_binding(base,wave,selected)
        return
    from .reset_failure_continuation import ResetFailureContinuation
    from .unattempted_subset_continuation import UnattemptedSubsetContinuation
    if type(authority) in (ResetFailureContinuation,UnattemptedSubsetContinuation):
        authority.require_guard_binding(base,wave,selected)
        return
    from .hardware_failure_continuation import HardwareFailureContinuation
    from .interrupted_setup_continuation import InterruptedSetupContinuation
    if type(authority) in (HardwareFailureContinuation,InterruptedSetupContinuation):
        authority.require_guard_binding(base,wave,selected)
        return
    from .constructor_continuation import ConstructorContinuation
    from .preinference_continuation import PreInferenceContinuation
    if type(authority) not in (InitializationContinuation,ConstructorContinuation,PreInferenceContinuation,HardwareFailureContinuation):raise ValueError('A validated explicit continuation is required')
    authority.require_guard_binding(base,wave,selected)


def require_runner_authority(authority,manifest,out,selected):
    from .surface_png_continuation import SurfacePngContinuation
    if type(authority) is SurfacePngContinuation:
        authority.validate_runner_selection(manifest,out,selected)
        return
    from .surface_path_continuation import SurfacePathContinuation
    if type(authority) is SurfacePathContinuation:
        authority.validate_runner_selection(manifest,out,selected)
        return
    from .terminal_capture_continuation import TerminalCaptureContinuation
    if type(authority) is TerminalCaptureContinuation:
        authority.validate_runner_selection(manifest,out,selected)
        return
    from .reset_failure_continuation import ResetFailureContinuation
    from .unattempted_subset_continuation import UnattemptedSubsetContinuation
    if type(authority) in (ResetFailureContinuation,UnattemptedSubsetContinuation):
        authority.validate_runner_selection(manifest,out,selected)
        return
    from .hardware_failure_continuation import HardwareFailureContinuation
    from .interrupted_setup_continuation import InterruptedSetupContinuation
    if type(authority) in (HardwareFailureContinuation,InterruptedSetupContinuation):
        authority.validate_runner_selection(manifest,out,selected)
        return
    from .constructor_continuation import ConstructorContinuation
    from .preinference_continuation import PreInferenceContinuation
    if type(authority) not in (InitializationContinuation,ConstructorContinuation,PreInferenceContinuation,HardwareFailureContinuation):raise ValueError('A validated explicit continuation is required')
    authority.validate_runner_selection(manifest,out,selected)
