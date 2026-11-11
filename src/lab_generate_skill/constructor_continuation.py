"""Evidence-bound continuation of constructor failures before model inference.

Sources and counts come from an immutable ordinary first claim, never from a
benchmark-specific task list. This is not a model retry flag: exact complete
closed raw bytes, frozen constructor AST and the reviewed directory-only fix
are prerequisites, as are the ordinary fresh source/proof/alias guards.
"""
import ast, hashlib, json, os, re
from copy import deepcopy
from pathlib import Path, PurePosixPath
from .initialization_continuation import (InitializationContinuation, pinned,
    regular_bytes, digest, archive_bytes)
from .io_utils import atomic_write_json
VERSION='constructor-zero-inference-continuation-v1'
CONTINUATION_ID='constructor-continuation-1'
FORBIDDEN=re.compile(r'^(generation|partial[-_]generation|actor[-_]input|actor[-_]budget|actor[-_]protocol|rollout|trajectory|step(?:[-_.]|$)|model[-_]loaded|inference[-_]started)',re.I)
SOURCE_NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}')
GLOBAL_FILES={'executed-code.json','pre-inference-assets.json','scope.json','summary.json'}


def _function(code, member, name, class_name=None):
    tree=ast.parse(code[member])
    parent=tree
    if class_name:
        classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name]
        if len(classes)!=1:raise ValueError('Exact frozen constructor class required')
        parent=classes[0]
    functions=[n for n in parent.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(functions)!=1:raise ValueError('Exact frozen constructor function required')
    return functions[0]


def _call_name(call):
    return ast.unparse(call.func)


def verify_constructor(code, failure):
    """Verify the complete recorded native call chain before every load site."""
    if failure.get('kind')!='exclusive-directory-constructor-v1' or failure.get('exception_type')!='FileExistsError':
        raise ValueError('Only the reviewed exclusive-directory constructor failure is supported')
    frames=failure.get('native_frames')
    if not isinstance(frames,list) or not 2<=len(frames)<=8:raise ValueError('Bounded complete frozen native frame chain required')
    for frame in frames:
        member=frame['member']; p=PurePosixPath(member)
        if p.is_absolute()or '..'in p.parts or member not in code or not member.endswith('.py'):raise ValueError('Actual frozen constructor member required')
        fn=_function(code,member,frame['function'],frame.get('class'))
        calls=[c for c in ast.walk(fn) if isinstance(c,ast.Call) and c.lineno==frame['line'] and _call_name(c)==frame['callee']]
        if len(calls)!=1:raise ValueError('Recorded frozen constructor call frame differs')
    root=frames[0]
    if root['member']!='scripts/run_site_navigation_once.py' or root['function']!='main' or root.get('class'):
        raise ValueError('Ordinary runner constructor frame required')
    main=_function(code,root['member'],'main')
    sensitive={'factory','load_backend','TransformersChatBackend','configure_actor'}
    loads=[c.lineno for c in ast.walk(main) if isinstance(c,ast.Call) and
           (_call_name(c) in sensitive or isinstance(c.func,ast.Attribute) and c.func.attr in {'acquire','_load','from_pretrained','generate','infer','chat','complete'})]
    if not loads or root['line']>=min(loads):raise ValueError('Frozen constructor must precede every model acquisition/load/inference call')
    mkdir=[c for c in ast.walk(main) if isinstance(c,ast.Call) and _call_name(c)=='dest.mkdir' and c.lineno<root['line']]
    if len(mkdir)!=1 or not any(k.arg=='exist_ok' and isinstance(k.value,ast.Constant)and k.value.value is True for k in mkdir[0].keywords):
        raise ValueError('Runner must already own the directory before the constructor')
    leaf=frames[-1]
    if leaf['callee']!='self.directory.mkdir':raise ValueError('Failure must be the native exclusive constructor mkdir')
    fn=_function(code,leaf['member'],leaf['function'],leaf.get('class'))
    mkdir=[c for c in ast.walk(fn) if isinstance(c,ast.Call) and c.lineno==leaf['line'] and _call_name(c)=='self.directory.mkdir'][0]
    kw={k.arg:k.value for k in mkdir.keywords}
    if set(kw)!={'parents','exist_ok'} or not all(isinstance(v,ast.Constant)for v in kw.values())or kw['parents'].value is not True or kw['exist_ok'].value is not False:
        raise ValueError('Native constructor must exclusively create its directory')
    # The failing native leaf accepts the same passed directory, not another
    # task's path. Intermediate calls must forward the directory argument.
    for frame in frames[1:-1]:
        fn=_function(code,frame['member'],frame['function'],frame.get('class'))
        call=next(c for c in ast.walk(fn) if isinstance(c,ast.Call)and c.lineno==frame['line']and _call_name(c)==frame['callee'])
        if not call.args or not isinstance(call.args[-1],ast.Name)or call.args[-1].id!='directory':
            raise ValueError('Actual constructor chain must forward the original directory')
    assignments=[n for n in ast.walk(fn if len(frames)==2 else _function(code,leaf['member'],leaf['function'],leaf.get('class'))) if isinstance(n,ast.Assign)]
    if not any(any(ast.unparse(t)=='self.directory'for t in n.targets)and ast.unparse(n.value)=='Path(directory)'for n in assignments):
        raise ValueError('Native mkdir must use its actual directory argument')


def verify_directory_fix(code, failure, fix):
    """Only change the constructor's child path, preserving the full old AST."""
    member=fix['member']; original=code[member]
    if hashlib.sha256(original).hexdigest()!=fix['old_sha256']:raise ValueError('Repair old frozen module differs')
    replacement=pinned(fix['path'],fix['new_sha256'])
    old=ast.parse(original);new=ast.parse(replacement)
    leaf=fix['leaf']
    if not isinstance(leaf,str)or not SOURCE_NAME.fullmatch(leaf):raise ValueError('Unique safe native child directory required')
    def locate(tree):
        parent=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==fix['class']) if fix.get('class') else tree
        return next(n for n in parent.body if isinstance(n,ast.FunctionDef)and n.name==fix['function'])
    old_fn,new_fn=locate(old),locate(new)
    select=lambda fn:[c for c in ast.walk(fn)if isinstance(c,ast.Call)and _call_name(c)==fix['callee']]
    oc,nc=select(old_fn),select(new_fn)
    if len(oc)!=1 or len(nc)!=1 or not isinstance(fix['arg_index'],int)or fix['arg_index']<0 or len(oc[0].args)<=fix['arg_index']or len(nc[0].args)<=fix['arg_index']:
        raise ValueError('Exact repaired constructor call required')
    i=fix['arg_index']
    if ast.unparse(oc[0].args[i])!='directory' or ast.unparse(nc[0].args[i])!=f"Path(directory) / {leaf!r}":
        raise ValueError('Repair must use a unique native child of the runner directory')
    nc[0].args[i]=ast.Name(id='directory',ctx=ast.Load())
    new.body=[n for n in new.body if not(isinstance(n,ast.ImportFrom)and n.module=='pathlib'and len(n.names)==1 and n.names[0].name=='Path'and n.names[0].asname is None)]
    # Preserve a pre-existing Path import rather than removing its original.
    for index,node in enumerate(old.body):
        if isinstance(node,ast.ImportFrom)and node.module=='pathlib'and len(node.names)==1 and node.names[0].name=='Path'and node.names[0].asname is None:
            new.body.insert(index,deepcopy(node))
    if ast.dump(old,include_attributes=False)!=ast.dump(new,include_attributes=False):raise ValueError('Directory repair changed unrelated frozen behavior')
    bridge=failure['native_frames'][-2]
    if member!=bridge['member']or fix['function']!=bridge['function']or fix.get('class')!=bridge.get('class')or fix['callee']!=bridge['callee']:
        raise ValueError('Repair must fix the actual failing constructor chain')
    return replacement


def zero_inference_raw(raw, code, sources, job, failure, manifest_sha):
    if any(FORBIDDEN.match(PurePosixPath(n).name)for n in raw):raise ValueError('Any inference/input/step/rollout marker prevents continuation')
    expected=GLOBAL_FILES|{s+'/'+n for s in sources for n in ('attempt-started.json','result.json')}
    if set(raw)!=expected:raise ValueError('Exact complete constructor-only raw outputs required; no unknown partial artifacts')
    verify_constructor(code,failure)
    producer=_function(code,'scripts/run_site_actor_bundle.py','run')
    ordinary_calls=[c for c in ast.walk(producer)if isinstance(c,ast.Call)and _call_name(c)=='runner']
    expected_argv=ast.parse("['--root',str(root),'--manifest',record['manifest'],'--domain',plan['domain'],'--out',str(Path(record['wave'])/'actor/0')]",mode='eval').body
    if len(ordinary_calls)!=1 or len(ordinary_calls[0].args)!=1 or ast.dump(ordinary_calls[0].args[0],include_attributes=False)!=ast.dump(expected_argv,include_attributes=False)or [(k.arg,ast.unparse(k.value))for k in ordinary_calls[0].keywords]!=[('backend_holder','backend')]:
        raise ValueError('Frozen ordinary producer must preserve the original exact runner argv')
    expected_frames=[{'file':PurePosixPath(f['member']).name,'function':f['function'],'line':f['line']}for f in failure['native_frames']]+failure['stdlib_frames']
    claims={};results=[]
    for source in sources:
        claim=json.loads(raw[source+'/attempt-started.json']);result=json.loads(raw[source+'/result.json'])
        if claim!={'job':job,'task':source,'scripted':False}:raise ValueError('Actual unchanged original first-attempt bytes required')
        if result.get('task_id')!=source or result.get('status')!='runtime_or_contract_error'or result.get('rollout_saved')is not False or result.get('api_calls')!=0 or result.get('evaluation')!={'status':'unknown','reward':None}:
            raise ValueError('Only zero-inference closed constructor failures may continue')
        d=result.get('diagnostic',{})
        if d.get('type')!=failure['exception_type']or d.get('stage')!='site_navigation_attempt'or d.get('frames')!=expected_frames:
            raise ValueError('Exact frozen pre-model constructor failure stack required')
        claims[source]=raw[source+'/attempt-started.json'];results.append(result)
    summary=json.loads(raw['summary.json']);scope=json.loads(raw['scope.json']);assets=json.loads(raw['pre-inference-assets.json'])
    if summary.get('results')!=results or summary.get('api_calls')!=0 or summary.get('scripted')is not False:
        raise ValueError('Complete actual summary must close every unchanged source')
    if scope.get('api_calls')!=0 or scope.get('scripted')is not False or scope.get('actor_attempts_per_task')!=1 or scope.get('terminal_only_scoring')is not True or scope.get('images_sent_to_actor')is not False:
        raise ValueError('Original ordinary actor protocol required')
    if assets.get('ready')is not True or assets.get('actor_attempts')!=0 or assets.get('api_calls')!=0:
        raise ValueError('Actual pre-inference asset validation required')
    execution=json.loads(raw['executed-code.json'])
    expected_code={n:hashlib.sha256(v).hexdigest()for n,v in code.items()if n=='scripts/run_site_navigation_once.py'or n.startswith('src/lab_generate_skill/')and n.endswith('.py')and '/'not in n[len('src/lab_generate_skill/'): ]}
    tracked={}
    for name,sha in execution.get('files',{}).items():
        matches=[n for n in expected_code if name.endswith('/'+n)]
        if len(matches)!=1 or matches[0]in tracked:raise ValueError('Executed frozen native byte coverage differs')
        tracked[matches[0]]=sha
    if execution.get('job_id')!=job or execution.get('manifest_sha256')!=manifest_sha or tracked!=expected_code:
        raise ValueError('All executed frozen runner/native bytes must match actual packet')
    return claims


class ConstructorContinuation(InitializationContinuation):
    """Validated normal-origin authority; no source IDs or counts are hardcoded."""
    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('continuation_id')!=CONTINUATION_ID or s.get('api_calls')!=0 or s.get('old_model_generations')!=0:
            raise ValueError('Explicit reviewed zero-inference constructor spec required')
        wave=Path(s['wave']).absolute();bundle=Path(s['old_bundle']).absolute();base=Path(s['base']).absolute()
        if wave.parent!=base or bundle.parent!=base/'actor-bundles'or s['new_shared_out']!=str(wave/'actor'/CONTINUATION_ID):raise ValueError('Same original first claim with unique separate continuation output required')
        required={'submitted','original_claim','old_bundle_plan','old_bundle_claims','old_worker_state','old_local_output_state','raw_manifest','raw_receipt','old_worker'}
        if set(s['metadata_pins'])!=required:raise ValueError('Complete real old producer metadata required')
        paths={'original_claim':wave/'first-actor-claim/preflight.json','old_bundle_plan':bundle/'plan.json','old_bundle_claims':bundle/'claimed-waves.json','old_worker_state':bundle/'worker-state.json','old_local_output_state':bundle/'local-output-state.json','raw_manifest':wave/'actor/0/diagnostic-members.json','raw_receipt':wave/'actor/0/actor-archive-receipt.json'}
        if any(Path(s['metadata_pins'][n]['path']).absolute()!=p for n,p in paths.items()):raise ValueError('Original exact producer locations required')
        rows={n:json.loads(pinned(pin['path'],pin['sha256']))for n,pin in s['metadata_pins'].items()if n!='old_worker'}
        submitted=rows['submitted'];claim=rows['original_claim'];plan=rows['old_bundle_plan'];job=submitted.get('job_id')
        if not isinstance(job,str)or not re.fullmatch('[1-9][0-9]*',job)or self.terminal_query(job)!={job:'COMPLETED'}:raise ValueError('Actual old allocation must be authoritatively COMPLETED')
        command=submitted.get('command');tail=[s['metadata_pins']['old_worker']['path'],s['old_runtime_archive'],s['old_runtime_sha256'],str(bundle),s['metadata_pins']['old_bundle_plan']['sha256']]
        if not isinstance(command,list)or len(command)<7 or command[:2]!=['sbatch','--parsable']or command[-5:]!=tail or any(not isinstance(n,str)or not n.startswith('--')for n in command[2:-5]):raise ValueError('Exact actual original scheduler argv required')
        worker=pinned(s['metadata_pins']['old_worker']['path'],s['metadata_pins']['old_worker']['sha256'])
        if b'run_archived_site_actor_bundle.py'not in worker or b'run_guarded_runtime.py'not in worker:raise ValueError('Actual guarded ordinary first-attempt producer required')
        if submitted.get('runtime_archive_sha256',submitted.get('frozen_code_sha256'))!=s['old_runtime_sha256']:raise ValueError('Submitted old packet hash differs')
        if plan.get('waves')!=[claim]or rows['old_bundle_claims']!=[claim]or plan.get('base')!=str(base)or plan.get('domain')!=claim.get('domain')or claim.get('wave')!=str(wave)or claim.get('manifest')!=str(wave/'admitted-tasks.jsonl'):
            raise ValueError('Original same-site first-claim provenance differs')
        if digest(claim['manifest'])!=claim['manifest_sha256']or digest(wave/'contracts.jsonl')!=claim['contracts_sha256']or digest(base/'inventory.jsonl')!=claim['inventory_sha256']:
            raise ValueError('Original manifest/contract/inventory drift')
        contracts=[json.loads(n)for n in regular_bytes(claim['manifest']).decode().splitlines()]
        sources=[c['task_id']for c in contracts];count=len(sources)
        if not 1<=count<=32 or len(set(sources))!=count or any(not SOURCE_NAME.fullmatch(n)for n in sources)or s.get('sources')!=sources or plan.get('tasks')!=count or claim.get('tasks')!=count:
            raise ValueError('One to 32 exact unchanged original claimed sources required')
        if any(c.get('source_task_id',c['task_id'])!=c['task_id']or c.get('domain')!=claim['domain']for c in contracts)or claim.get('api_calls')!=0 or plan.get('api_calls')!=0 or claim.get('actor_attempts_per_source')!=1:
            raise ValueError('Only unchanged original same-site first-attempt contracts may continue')
        if [r['source_task_id']for r in claim['proofs']]!=sources:raise ValueError('All original proof identities required')
        for proof in claim['proofs']:
            pinned(proof['file'],proof['sha256'])
        project=Path(s['current_runtime_project']).absolute()
        if project!=base.parent.parent/'TFcode-generate-skill/Lab_generate_skill':raise ValueError('Canonical current source policy project required')
        from build_map_osm_export_capability import active_scope
        if Path(active_scope(project)['scope_manifest']).absolute()!=Path(s['source_policy_pin']['path']).absolute():raise ValueError('Current source policy pointer drift')
        policy=json.loads(pinned(s['source_policy_pin']['path'],s['source_policy_pin']['sha256']))
        from prepare_admitted_site_actor import inventory_aliases
        inventory=[json.loads(n)for n in regular_bytes(base/'inventory.jsonl').decode().splitlines()]
        aliases=inventory_aliases(inventory);excluded=set(policy['external_excluded_task_ids'])|set(policy['heldout_overlap_quarantined_task_ids'])
        if any(source not in aliases or aliases[source]&excluded for source in sources):raise ValueError('Current alias/external/heldout scope excludes an original source')
        state=rows['old_worker_state'];local=rows['old_local_output_state']
        if state.get('status')!='completed'or state.get('api_calls')!=0 or state.get('completed_waves')!=[{'wave':str(wave),'tasks':count,'result_records':count}]:raise ValueError('Every old source must be authoritatively closed')
        if local.get('bundle')!=str(bundle)or local.get('plan_sha256')!=s['metadata_pins']['old_bundle_plan']['sha256']or set(local.get('waves',{}))!={str(wave)}or local['waves'][str(wave)].get('status')!='runner_closed'or local['waves'][str(wave)].get('task_ids')!=sources:
            raise ValueError('Actual old worker local-output closure required')
        code=archive_bytes(s['old_runtime_archive'],s['old_runtime_sha256'])
        raw=archive_bytes(s['raw_archive'],s['raw_archive_sha256'],s['metadata_pins']['raw_manifest']['path'],s['metadata_pins']['raw_manifest']['sha256'])
        manifest=rows['raw_manifest'];receipt=rows['raw_receipt']
        for row in (manifest,receipt):
            if row.get('archive_sha256')!=s['raw_archive_sha256']or row.get('member_count')!=len(raw)or row.get('full_output_not_sampled')is not True:raise ValueError('Complete unchanged raw archive and closure required')
        if manifest.get('archival_status')!='complete_member_archive_saved'or len(raw)!=2*count+len(GLOBAL_FILES):raise ValueError('Complete constructor-only member coverage required')
        claims=zero_inference_raw(raw,code,sources,job,s['failure'],claim['manifest_sha256'])
        verify_directory_fix(code,s['failure'],s['fix'])
        self.allowed_old_artifacts={}
        if [r['task_id']for r in receipt['tasks']]!=sources or any(r.get('first_completed_generation_member')is not None or r.get('copied_raw_members')!=[r['task_id']+'/result.json']for r in receipt['tasks']):raise ValueError('Every actual archive receipt must certify no completed inference')
        for source in sources:
            result=wave/'actor/0'/source/'result.json';marker=wave/'actor/0'/source/'attempt-archive.json'
            if regular_bytes(result)!=raw[source+'/result.json']:raise ValueError('Retained old failure bytes changed')
            m=json.loads(regular_bytes(marker))
            if m.get('task_id')!=source or m.get('archive_sha256')!=s['raw_archive_sha256']or m.get('first_completed_generation_member')is not None or m.get('raw_member_count')!=2 or m.get('automatic_retry')is not False or m.get('actor_calls_by_archive')!=0 or m.get('copied_raw_members')!=[source+'/result.json']:raise ValueError('Actual retained original attempt marker differs')
            for p in(result,marker):self.allowed_old_artifacts[p.absolute()]=digest(p)
        if {Path(p['path']).absolute()for p in s['retained_marker_pins'].values()}!=set(self.allowed_old_artifacts):raise ValueError('Every exact old result/archive marker must stay pinned')
        for pin in s['retained_marker_pins'].values():pinned(pin['path'],pin['sha256'])
        for d in(wave/'first-actor-claim/worker-started',bundle/'worker-started'):
            if d.is_symlink()or not d.is_dir()or any(d.iterdir()):raise ValueError('Original worker claim must remain unchanged')
        lease=wave/'first-actor-claim'/CONTINUATION_ID
        if lease.exists()and(self.lease is None or lease!=self.lease or digest(lease/'lease.json')!=self.lease_digest):raise ValueError('Constructor continuation already has an exclusive owner')
        self.wave,self.bundle,self.claim,self.raw,self.code,self.old_job=wave,bundle,claim,raw,code,job
        self.contracts,self.sources,self.old_claim_bytes=contracts,sources,claims
        return claim

    def start(self,bundle,local_out,*,manifest_path):
        self.validate_current_admission();bundle=Path(bundle).absolute();local_out=Path(local_out).absolute()
        job=os.environ.get('SLURM_JOB_ID')
        if not isinstance(job,str)or not re.fullmatch('[1-9][0-9]*',job)or job==self.old_job:raise ValueError('New real allocation must own the exact constructor continuation')
        if bundle.parent!=self.wave.parent/'actor-bundles'or bundle==self.bundle or bundle.exists():raise ValueError('New unique continuation bundle required')
        project=Path(__file__).absolute().parents[2]
        if digest(project/self.spec['fix']['member'])!=self.spec['fix']['new_sha256']:raise ValueError('Actual executing frozen runtime does not contain the reviewed constructor repair')
        from .native_runtime_assets import preflight
        report=preflight(project,self.contracts,manifest_path=manifest_path)
        if local_out.is_symlink()or not local_out.is_dir()or any(local_out.iterdir()):raise ValueError('Unique empty owned local continuation output required')
        lease=self.wave/'first-actor-claim'/CONTINUATION_ID
        lease.mkdir(mode=0o700);self.lease=lease
        record={'version':VERSION,'old_job':self.old_job,'old_first_claim_sha256':self.spec['metadata_pins']['original_claim']['sha256'],
            'spec_sha256':hashlib.sha256(json.dumps(self.spec,sort_keys=True).encode()).hexdigest(),'bundle':str(bundle),'local_out':str(local_out),
            'shared_out':self.spec['new_shared_out'],'job':job,'pid':os.getpid(),'sources':self.sources,
            'first_model_inference_continues_existing_claim':True,'automatic_retry':False}
        atomic_write_json(lease/'lease.json',record);self.lease_digest=digest(lease/'lease.json');self.local_out=local_out
        bundle.mkdir(mode=0o700);atomic_write_json(bundle/'plan.json',{'version':VERSION,'spec':self.spec,'lease':record,'assets':report})
        return record

    def begin_source(self,contract,directory):
        task=contract.get('task_id');directory=Path(directory).absolute()
        if self.lease is None:raise ValueError('Exclusive same-first-claim continuation lease required')
        record=json.loads(regular_bytes(self.lease/'lease.json'))
        if digest(self.lease/'lease.json')!=self.lease_digest or record.get('pid')!=os.getpid()or record.get('job')!=os.environ.get('SLURM_JOB_ID'):raise ValueError('Only exact live lease owner may continue initialization')
        if task not in self.sources or directory!=self.local_out/task or task in self.started or self.contracts[len(self.started)]!=contract:raise ValueError('One ordered unchanged source continuation required')
        self.verify_origin()
        if directory.is_symlink()or not directory.is_dir()or any(directory.iterdir()):raise ValueError('Never replace current source outputs or inference')
        with(directory/'attempt-started.json').open('xb')as f:f.write(self.old_claim_bytes[task])
        atomic_write_json(directory/'constructor-continuation.json',{'version':VERSION,'old_first_claim_sha256':self.spec['metadata_pins']['original_claim']['sha256'],
            'old_attempt_claim_sha256':hashlib.sha256(self.old_claim_bytes[task]).hexdigest(),'lease':str(self.lease),'lease_sha256':self.lease_digest,
            'source_task_id':task,'current_job':os.environ.get('SLURM_JOB_ID'),'old_job':self.old_job,'first_model_generation':True,'actor_failure_retry':False})
        self.started.append(task)
