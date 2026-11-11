"""Explicit continuation of a closed hook failure before the first model load.

No source list is hardcoded. Complete task archives and the frozen runner's
recorded failure location must prove zero inference; ordinary admission and
source/split guards still run. Old artifacts and claims are never replaced.
"""
import ast
import hashlib
import json
import os
from lab_generate_skill.slurm_allocation_identity import allocation_tmpdir_matches
from pathlib import Path
from copy import deepcopy
from .initialization_continuation import InitializationContinuation, pinned, digest, regular_bytes, archive_bytes
from .constructor_continuation import FORBIDDEN
from .io_utils import atomic_write_json

VERSION = 'closed-preinference-hook-continuation-v1'
LEASE = 'preinference-hook-continuation-1'


def verify_native_resource_failure(frames, files):
    """Bind the observed resource-read stack to the executed Python sources.

    This admits a missing local PHP reader, never a failed database command or
    a generic FileNotFoundError from inside model execution.
    """
    chain = [
        ('public_completion_runtime.py', 'NativeReadHooks', 'prepare', 'self.delegate.verify_baseline'),
        ('shopping_native_three_runtime.py', 'NativeThreeHooks', 'verify_baseline', 'protected_state'),
        ('shopping_native_three_runtime.py', None, 'protected_state', 'protected'),
        ('probe_shopping_seven_native.py', None, 'protected', 'php.read_text'),
    ]
    if (len(frames) != 7 or set(files) != {x[0] for x in chain}
            or [(f.get('file'), f.get('function')) for f in frames[-2:]]
            != [('pathlib.py', 'read_text'), ('pathlib.py', 'open')]):
        raise ValueError('Exact recorded native resource-read stack required')
    for frame, (filename, cls, function, call) in zip(frames[1:5], chain):
        tree = ast.parse(files[filename])
        scope = tree if cls is None else next((n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == cls), None)
        functions = [] if scope is None else [n for n in scope.body
            if isinstance(n, ast.FunctionDef) and n.name == function]
        if len(functions) != 1 or (frame.get('file'), frame.get('function')) != (filename, function):
            raise ValueError('Native resource failure source differs')
        calls = [n for n in ast.walk(functions[0]) if isinstance(n, ast.Call)]
        if not any(n.lineno == frame.get('line') and ast.unparse(n.func) == call for n in calls):
            raise ValueError('Native resource failure line differs')
        if any(isinstance(n.func, ast.Attribute) and n.func.attr in
               {'acquire', 'generate', 'infer', 'chat', 'complete', 'from_pretrained', '_load'}
               for n in calls):
            raise ValueError('Model work inside resource preparation is not retryable')
        if filename == 'probe_shopping_seven_native.py':
            first = functions[0].body[0]
            if (not isinstance(first, ast.Assign) or len(first.targets) != 1
                    or ast.unparse(first.targets[0]) != 'php'
                    or ast.unparse(first.value) != "Path(__file__).resolve().parents[1] / 'src/lab_generate_skill/shopping_seven_protection.php'"):
                raise ValueError('Exact packaged PHP resource path required')


def verify_preload_failure(raw, runner, task, job, *, native_hook=None, native_resource_files=None, query_guard_proof=None):
    if any(FORBIDDEN.match(Path(name).name) for name in raw):
        raise ValueError('Inference artifacts prohibit pre-inference continuation')
    required = {'result.json', 'attempt-started.json'}
    if not required <= set(raw):
        raise ValueError('Closed actual source attempt and result required')
    result = json.loads(raw['result.json']); claim = json.loads(raw['attempt-started.json'])
    if claim != {'job': job, 'task': task, 'scripted': False}:
        raise ValueError('Original task/job attempt binding differs')
    if (result.get('task_id') != task or result.get('status') != 'runtime_or_contract_error'
            or result.get('evaluation') != {'status': 'unknown', 'reward': None}
            or result.get('rollout_saved') is not False or result.get('api_calls') != 0):
        raise ValueError('Only closed pre-inference runtime errors may continue')
    frames = result.get('diagnostic', {}).get('frames', [])
    if result.get('diagnostic', {}).get('stage') != 'site_navigation_attempt' or not frames:
        raise ValueError('Original ordinary-runner exception location required')
    main = next(n for n in ast.parse(runner).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    frame = frames[0]
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)]
    loads = [n.lineno for n in calls if ast.unparse(n.func) in {'load_backend', 'factory', 'configure_actor'}
             or isinstance(n.func, ast.Attribute) and n.func.attr in {'acquire', 'from_pretrained', 'generate', 'infer', 'chat', 'complete', '_load'}]
    if query_guard_proof is not None:
        # The exception is a missing legacy fingerprint key in the actual
        # runner's baseline comparison, not a call into a model or hook.
        guards = [n for n in ast.walk(main) if isinstance(n, ast.If)
                  and n.lineno == frame.get('line')]
        expected = ast.parse("native_read_hooks is None and not any(c.get(k) for k in ('membership','preferences','cart','vote','native_csv_export','map_native_layer')) and before != proof['cycles'][0]['initial_fingerprint']", mode='eval').body
        cycles = query_guard_proof.get('cycles', [])
        if (result.get('domain') != 'reddit' or len(frames) != 1
                or result['diagnostic'].get('type') != 'KeyError'
                or frame.get('file') != 'run_site_navigation_once.py'
                or frame.get('function') != 'main' or len(guards) != 1
                or not loads or frame['line'] >= min(loads)
                or ast.dump(guards[0].test) != ast.dump(expected)
                or set(raw) != {'attempt-started.json','query-baseline.json','result.json'}
                or query_guard_proof.get('task_id') != task
                or query_guard_proof.get('admission_version') != 'site-query-admission-v1'
                or query_guard_proof.get('passed') is not True
                or query_guard_proof.get('sql_and_native_ui_verified') is not True
                or query_guard_proof.get('reset_mode') != 'two_full_restores_same_factory'
                or not query_guard_proof.get('original_capture_archive')
                or len(cycles) != 2 or not all(isinstance(c,dict) for c in cycles)
                or 'initial_fingerprint' in cycles[0]):
            raise ValueError('Exact recorded missing query baseline before inference required')
        return claim
    at_failure = [n for n in calls if n.lineno == frame.get('line')]
    if (frame.get('function') != 'main' or frame.get('file') not in {'runner.py', 'run_site_navigation_once.py'}
            or len(at_failure) != 1 or not loads or frame['line'] >= min(loads)):
        raise ValueError('Recorded failing call must precede every model acquisition and inference')
    function = ast.unparse(at_failure[0].func)
    if function == 'native_read_hooks.prepare' and result['diagnostic'].get('type') == 'FileNotFoundError':
        verify_native_resource_failure(frames, native_resource_files or {})
        return claim
    if function == 'native_read_hooks.prepare':
        # A profile mismatch before any model acquisition is not an actor
        # attempt. Bind the *actual executed hook*, not merely its filename.
        if (native_hook is None or len(frames)!=2 or frames[1].get('file')!='map_share_observation.py'
                or frames[1].get('function')!='prepare' or result['diagnostic'].get('type')!='ValueError'):
            raise ValueError('Actual native profile failure code required')
        tree=ast.parse(native_hook)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='ShareObservationHooks')
        prepare=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='prepare')
        leaf=[n for n in ast.walk(prepare)if isinstance(n,ast.Raise)and n.lineno==frames[1].get('line')]
        if (len(leaf)!=1 or ast.unparse(leaf[0].exc)!="ValueError('Full guarded Map share-observer profile required')"):
            raise ValueError('Only the exact observed environment-profile guard may continue')
        earlier_calls=[ast.unparse(n.func)for n in ast.walk(prepare)if isinstance(n,ast.Call)and n.lineno<leaf[0].lineno]
        if set(earlier_calls)-{'ValueError','all','getattr'}:
            raise ValueError('Unverified work precedes the profile guard')
        return claim
    if (function == 'native_read_runtime.owns_csv_transport'
            and len(frames) == 1 and result['diagnostic'].get('type') == 'AttributeError'):
        # The attribute lookup failed in the runner, before entering any hook
        # or acquiring a model. This is an interface-binding repair, not an
        # actor retry. Archive, allocation, admission and exclusive lease
        # requirements below still apply unchanged.
        return claim
    if function != 'native_csv_runtime.owned_transport':
        raise ValueError('Unreviewed pre-inference failure kind')
    if len(frames) != 2 or frames[1].get('function') != 'owned_transport' or result['diagnostic'].get('type') != 'ValueError':
        raise ValueError('Exact reviewed lifecycle handoff failure required')
    return claim


class PreInferenceContinuation(InitializationContinuation):
    def verify_origin(self):
        s = self.spec
        if s.get('version') != VERSION or s.get('api_calls') != 0:
            raise ValueError('Explicit pinned pre-inference continuation spec required')
        rows = {k: json.loads(pinned(v['path'], v['sha256'])) for k, v in s['pins'].items()}
        wave = Path(s['wave']).resolve(); bundle = Path(s['old_bundle']).resolve()
        claim = rows['claim']; plan = rows['plan']; state = rows['state']; closure = rows['closure']
        job = s['old_job']; scheduler_job = s.get('old_scheduler_job', job)
        if scheduler_job != job and not (s.get('native_resource_files') or s.get('query_guard_proof')):
            raise ValueError('Array identity requires the original submitted producer')
        status = self.terminal_query(scheduler_job)
        if status.get(scheduler_job) not in {'COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED', 'NODE_FAIL', 'OUT_OF_MEMORY'}:
            raise ValueError('Old exact allocation must be terminal')
        expected_paths = {'claim': wave/'first-actor-claim/preflight.json', 'plan': bundle/'plan.json',
                          'state': bundle/'worker-state.json', 'closure': bundle/'actor-storage-exit.json',
                          'local': bundle/'local-output-state.json'}
        if any(Path(s['pins'][k]['path']).resolve() != v for k, v in expected_paths.items()):
            raise ValueError('Original producer metadata locations differ')
        if (bundle.parent != wave.parent/'actor-bundles' or plan['waves'] != [claim]
                or claim['wave'] != str(wave) or plan.get('api_calls') != 0
                or closure.get('owned_writers_quiet') is not True or closure.get('cleanup_error') is not None
                or closure.get('actor_restarted') is not False or closure.get('actor_calls_by_recovery') != 0
                or not allocation_tmpdir_matches(job, closure['retained_node_local_tmpdir'])):
            raise ValueError('Exact closed original bundle required')
        local = rows['local']
        if (local.get('services_closed') is not True or local.get('bundle') != str(bundle)
                or local.get('plan_sha256') != s['pins']['plan']['sha256']
                or set(local['waves']) != {str(wave)} or local['waves'][str(wave)]['status'] != 'runner_closed'):
            raise ValueError('Original output and services must be closed')
        for field, path in [('manifest', Path(claim['manifest'])), ('contracts', wave/'contracts.jsonl'),
                            ('inventory', wave.parent/'inventory.jsonl')]:
            if digest(path) != claim[field+'_sha256']:
                raise ValueError('Original task, proof, inventory or split binding changed')
        contracts = [json.loads(line) for line in regular_bytes(claim['manifest']).decode().splitlines()]
        sources = [c['task_id'] for c in contracts]
        if not 1 <= len(sources) <= 32 or len(set(sources)) != len(sources) or set(s['tasks']) != set(sources):
            raise ValueError('All and only original source attempts may continue')
        if (state.get('status') != 'completed' or state.get('api_calls') != 0
                or state.get('completed_waves') != [{'wave':str(wave),'tasks':len(sources),'result_records':len(sources)}]):
            raise ValueError('Original worker must have closed every source')
        for p in claim['proofs']:
            pinned(p['file'], p['sha256'])
        runner = pinned(s['runner']['path'], s['runner']['sha256'])
        execution = rows['execution']
        executed_runner=s['runner'].get('executed_path',s['runner']['path'])
        if execution.get('job_id') != job or execution.get('manifest_sha256') != claim['manifest_sha256'] or execution.get('files', {}).get(executed_runner) != s['runner']['sha256']:
            raise ValueError('Recorded actual frozen runner identity required')
        hook=None
        if s.get('native_hook') is not None:
            pin=s['native_hook'];hook=pinned(pin['path'],pin['sha256'])
            if execution.get('files',{}).get(pin['executed_path'])!=pin['sha256']:
                raise ValueError('Recorded actual frozen hook identity required')
        resource_files = {}
        producer_members = {}
        if s.get('native_resource_files') or s.get('query_guard_proof'):
            producer = s.get('producer', {})
            if set(producer) != {'launch', 'batch', 'submitted', 'capsule'}:
                raise ValueError('Original frozen resource producer required')
            original = {k: json.loads(pinned(v['path'], v['sha256'])) for k,v in producer.items()}
            workers = original['batch']['workers']
            indexes = [i for i,w in enumerate(workers)
                       if w['bundle'] == str(bundle) and w['plan_sha256'] == s['pins']['plan']['sha256']]
            if (original['launch'].get('batch') != producer['batch']
                    or original['launch'].get('capsule') != producer['capsule']
                    or original['submitted'].get('job_id') != job
                    or len(indexes) != 1
                    or scheduler_job != job+'_'+str(indexes[0])):
                raise ValueError('Resource producer is not the original submitted bundle')
            producer_members = original['capsule']['members']
            if s.get('native_resource_files') and 'src/lab_generate_skill/shopping_seven_protection.php' in producer_members:
                raise ValueError('Missing PHP resource was present in the original capsule')
            if producer_members.get('scripts/run_site_navigation_once.py', {}).get('sha256') != s['runner']['sha256']:
                raise ValueError('Original executed runner differs from resource capsule')
        for name, pin in s.get('native_resource_files', {}).items():
            member = pin.get('member', '')
            expected_path = str(Path(executed_runner).parent.parent / member)
            if (Path(member).name != name or pin['executed_path'] != expected_path
                    or producer_members.get(member, {}).get('sha256') != pin['sha256']
                    or execution.get('files', {}).get(expected_path, pin['sha256']) != pin['sha256']):
                raise ValueError('Recorded actual native resource reader identity required')
            resource_files[name] = pinned(pin['path'], pin['sha256'])
        query_proof = None
        if s.get('query_guard_proof'):
            ref = s['query_guard_proof']
            if (len(contracts) != 1 or contracts[0].get('domain') != 'reddit'
                    or not contracts[0].get('query') or len(claim['proofs']) != 1
                    or ref != {'path': claim['proofs'][0]['file'], 'sha256': claim['proofs'][0]['sha256']}):
                raise ValueError('Original single query proof binding required')
            query_proof = json.loads(pinned(ref['path'],ref['sha256']))
            from .reddit_query_protection import expected
            # Re-read and verify real complete13 records; no invented legacy key.
            expected(contracts[0],query_proof)
        self.old_claim_bytes = {}; self.allowed_old_artifacts = {}
        for task in sources:
            rec = s['tasks'][task]
            raw = archive_bytes(rec['archive'], rec['archive_sha256'], rec['index'], rec['index_sha256'])
            verify_preload_failure(raw, runner, task, job,native_hook=hook,native_resource_files=resource_files,query_guard_proof=query_proof)
            self.old_claim_bytes[task] = raw['attempt-started.json']
            if raw['result.json'] != regular_bytes(wave/'actor/0'/task/'result.json'):
                raise ValueError('Current retained error differs from closed raw archive')
            for name in ('result.json', 'attempt-archive.json'):
                path = wave/'actor/0'/task/name
                self.allowed_old_artifacts[path.resolve()] = digest(path)
            marker = json.loads(regular_bytes(wave/'actor/0'/task/'attempt-archive.json'))
            if marker.get('archive_sha256') != rec['archive_sha256'] or marker.get('first_completed_generation_member') is not None:
                raise ValueError('Task archive marker contradicts zero inference')
        expected = {str(k):v for k,v in self.allowed_old_artifacts.items()}
        if expected != s['retained_artifacts']:
            raise ValueError('Retained old evidence changed')
        if s['new_shared_out'] != str(wave/'actor'/LEASE):
            raise ValueError('Distinct continuation output required')
        if (wave/'first-actor-claim'/LEASE).exists() and self.lease is None:
            raise ValueError('Continuation already claimed')
        self.wave, self.bundle, self.claim, self.old_job = wave, bundle, claim, job
        self.contracts, self.sources = contracts, sources
        return claim

    def require_original_public_revision(self, authority, selected):
        """Preserve the prior goal revision; do not grant another revision."""
        from .public_completion_attempt import PublicCompletionAuthority
        if (type(authority) is not PublicCompletionAuthority or not self.ready
                or authority.wave != self.wave or authority.base != self.wave.parent
                or list(selected) != self.contracts
                or self.claim.get('answer_protocol_repair', {}).get('authorization_sha256') != authority.spec_sha
                or self.claim.get('previous_actor_attempts') != authority.previous_attempts):
            raise ValueError('Continuation must preserve the exact original public revision authority')

    def start(self, bundle, local_out, *, runtime_project, manifest_path):
        self.validate_current_admission()
        bundle = Path(bundle).resolve(); local_out = Path(local_out).resolve()
        job = os.environ.get('SLURM_JOB_ID')
        if not job or job == self.old_job or bundle == self.bundle or bundle.parent != self.wave.parent/'actor-bundles':
            raise ValueError('New allocated continuation worker and unique bundle required')
        plan = json.loads(regular_bytes(bundle/'plan.json'))
        binding = plan.get('preinference_continuation', {})
        if json.loads(pinned(binding['path'], binding['sha256'])) != self.spec or plan['waves'] != [self.claim]:
            raise ValueError('New bundle must bind this exact continuation and old claim')
        if not local_out.is_dir() or local_out.is_symlink() or any(local_out.iterdir()):
            raise ValueError('Empty isolated continuation output required')
        from .native_runtime_assets import preflight
        report = preflight(runtime_project, self.contracts, manifest_path=manifest_path)
        self.lease = self.wave/'first-actor-claim'/LEASE; self.lease.mkdir(mode=0o700)
        record = dict(version=VERSION,old_job=self.old_job,job=job,pid=os.getpid(),bundle=str(bundle),
                      local_out=str(local_out),shared_out=self.spec['new_shared_out'],sources=self.sources,
                      old_first_claim_sha256=self.spec['pins']['claim']['sha256'],automatic_retry=False)
        atomic_write_json(self.lease/'lease.json',record);self.lease_digest=digest(self.lease/'lease.json');self.local_out=local_out
        atomic_write_json(bundle/'continuation-start.json',dict(version=VERSION,lease=record,assets=report))
        return record

    def begin_source(self, contract, directory):
        task = contract['task_id']; directory = Path(directory).resolve()
        if self.lease is None or digest(self.lease/'lease.json') != self.lease_digest:
            raise ValueError('Exclusive continuation lease required')
        lease = json.loads(regular_bytes(self.lease/'lease.json'))
        if lease['pid'] != os.getpid() or lease['job'] != os.environ.get('SLURM_JOB_ID'):
            raise ValueError('Only live lease owner can continue')
        if task in self.started or directory != self.local_out/task or self.contracts[len(self.started)] != contract or any(directory.iterdir()):
            raise ValueError('One unchanged ordered source per continuation')
        self.verify_origin()
        with (directory/'attempt-started.json').open('xb') as f:f.write(self.old_claim_bytes[task])
        atomic_write_json(directory/'preinference-continuation.json',dict(version=VERSION,old_job=self.old_job,current_job=lease['job'],lease=str(self.lease),actor_failure_retry=False))
        self.started.append(task)
