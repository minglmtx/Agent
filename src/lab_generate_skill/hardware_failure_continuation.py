"""One explicit retry of a closed CUDA failure before any actor action.

A started generation is not called 'unstarted'. Original failures stay intact;
this authority permits a separately recorded runtime-repair attempt only after
full archive and scheduler checks. Successful or semantic actor failures cannot
use this path. The ordinary admission/split/alias checks remain mandatory.
"""
import hashlib
import json
import os
from lab_generate_skill.slurm_allocation_identity import allocation_tmpdir_matches
from pathlib import Path
from .initialization_continuation import InitializationContinuation, pinned, digest, regular_bytes, archive_bytes
from .io_utils import atomic_write_json

VERSION = 'closed-cuda-zero-action-repair-v1'
LEASE = 'hardware-repair-1'
BINDING = 'hardware_repair_continuation'


def verify_zero_action_cuda_failure(raw, task, job):
    def read(name):
        return json.loads(raw[name])
    claim = read('attempt-started.json')
    if claim != {'job': job, 'task': task, 'scripted': False}:
        raise ValueError('Original task/allocation binding required')
    result = read('result.json')
    if (result.get('task_id') != task or result.get('rounds') != 0
            or result.get('finish_reason') != 'runtime_error' or result.get('api_calls') != 0
            or result.get('evaluation', {}).get('status') != 'unknown'
            or result.get('evaluation', {}).get('reward') is not None
            or result.get('error', {}).get('type') != 'AcceleratorError'
            or result['error'].get('stage') != 'actor_generation'):
        raise ValueError('Only zero-action CUDA runtime errors qualify')
    generations = {n for n in raw if Path(n).name.startswith('generation-')}
    steps = {n for n in raw if Path(n).name.startswith('step-')}
    if generations != {'generation-000.json'} or steps != {'step-000.json'}:
        raise ValueError('Only the first interrupted generation and initial observation qualify')
    g = read('generation-000.json')
    if g.get('status') != 'started' or not set(g) <= {'status','messages','seed','input_tokens','observation_budget','max_new_tokens'}:
        raise ValueError('Completed or partial model output prohibits this repair')
    step = read('step-000.json')
    if step.get('step') != 0 or step.get('action') is not None:
        raise ValueError('Actor action already occurred')
    for name in ('trajectory.json', 'rollout-raw.json'):
        t = read(name)
        if (t.get('task_id') != task or t.get('rounds') != 0
                or t.get('finish_reason') != 'runtime_error'
                or t.get('generation_finish_reasons') != []
                or [m.get('role') for m in t.get('messages', [])] != ['user']
                or t.get('error') != result['error']):
            raise ValueError('Complete trajectory contradicts zero-action failure')
    if any(Path(n).name.startswith(('partial-generation','actor-output')) for n in raw):
        raise ValueError('Partial model output cannot be discarded')
    return claim


class HardwareFailureContinuation(InitializationContinuation):
    version=VERSION
    lease_name=LEASE
    binding_name=BINDING
    def verify_origin(self):
        s = self.spec
        if s.get('version') != VERSION or s.get('api_calls') != 0:
            raise ValueError('Explicit hardware repair spec required')
        wave = Path(s['wave']).resolve(); bundle = Path(s['old_bundle']).resolve(); job = s['old_job']
        if self.terminal_query(job).get(job) not in {'COMPLETED','FAILED','CANCELLED','TIMEOUT','NODE_FAIL','OUT_OF_MEMORY'}:
            raise ValueError('Prior exact allocation is not terminal')
        expected = {'claim':wave/'first-actor-claim/preflight.json', 'plan':bundle/'plan.json',
                    'state':bundle/'worker-state.json', 'local':bundle/'local-output-state.json',
                    'closure':bundle/'actor-storage-exit.json'}
        if (bundle.parent != wave.parent/'actor-bundles' or set(s['pins']) != set(expected)
                or any(Path(s['pins'][k]['path']).resolve() != p for k,p in expected.items())):
            raise ValueError('Original producer paths required')
        rows = {k:json.loads(pinned(v['path'],v['sha256'])) for k,v in s['pins'].items()}
        claim, plan, local, closure, state = (rows[k] for k in ('claim','plan','local','closure','state'))
        if (plan['waves'] != [claim] or claim['wave'] != str(wave) or plan.get('api_calls') != 0
                or local.get('services_closed') is not True or local.get('bundle') != str(bundle)
                or local.get('plan_sha256') != s['pins']['plan']['sha256']
                or set(local['waves']) != {str(wave)} or local['waves'][str(wave)]['status'] != 'runner_closed'
                or closure.get('owned_writers_quiet') is not True or closure.get('cleanup_error') is not None
                or closure.get('actor_restarted') is not False or closure.get('actor_calls_by_recovery') != 0
                or closure.get('archive_state') != str(bundle/'local-output-state.json')
                or not allocation_tmpdir_matches(job, closure['retained_node_local_tmpdir'])):
            raise ValueError('Closed original services, writers and exact plan required')
        log = pinned(s['log']['path'],s['log']['sha256']).decode()
        if Path(s['log']['path']).name != 'site-actor-bundle-'+job+'.log' or 'sm_120 is not compatible with the current PyTorch installation' not in log:
            raise ValueError('Actual allocation architecture incompatibility evidence required')
        for key,path in [('manifest',Path(claim['manifest'])),('contracts',wave/'contracts.jsonl'),('inventory',wave.parent/'inventory.jsonl')]:
            if digest(path) != claim[key+'_sha256']:
                raise ValueError('Original source/contract/split binding changed')
        self.contracts = [json.loads(line) for line in regular_bytes(claim['manifest']).decode().splitlines()]
        sources = [c['task_id'] for c in self.contracts]
        if not 1 <= len(sources) <= 32 or len(set(sources)) != len(sources) or set(s['tasks']) != set(sources):
            raise ValueError('All and only original tasks required')
        if state.get('status') != 'completed' or state.get('completed_waves') != [{'wave':str(wave),'tasks':len(sources),'result_records':len(sources)}]:
            raise ValueError('Every original runtime failure must be closed')
        for proof in claim['proofs']: pinned(proof['file'],proof['sha256'])
        self.allowed_old_artifacts = {}; self.old_claim_bytes = {}
        for task in sources:
            rec = s['tasks'][task]
            raw = archive_bytes(rec['archive'],rec['archive_sha256'],rec['index'],rec['index_sha256'])
            verify_zero_action_cuda_failure(raw,task,job)
            self.old_claim_bytes[task] = raw['attempt-started.json']
            marker_path = wave/'actor/0'/task/'attempt-archive.json'
            marker = json.loads(regular_bytes(marker_path))
            if (marker.get('archive_path') != rec['archive'] or marker.get('archive_sha256') != rec['archive_sha256']
                    or marker.get('first_completed_generation_member') is not None
                    or marker.get('raw_member_count') != len(raw)):
                raise ValueError('Complete task archive marker differs')
            for name in ('result.json','trajectory.json','trajectory.md','terminal-page.json'):
                path = wave/'actor/0'/task/name
                if regular_bytes(path) != raw[name]:
                    raise ValueError('Retained original artifact differs from archive')
                self.allowed_old_artifacts[path.resolve()] = digest(path)
            self.allowed_old_artifacts[marker_path.resolve()] = digest(marker_path)
        if s['retained_artifacts'] != {str(k):v for k,v in self.allowed_old_artifacts.items()}:
            raise ValueError('Old artifacts changed')
        if s['new_shared_out'] != str(wave/'actor'/LEASE):
            raise ValueError('Distinct runtime-repair output required')
        if (wave/'first-actor-claim'/LEASE).exists() and self.lease is None:
            raise ValueError('Hardware repair already claimed')
        self.wave, self.bundle, self.claim, self.old_job = wave, bundle, claim, job
        self.sources = sources
        return claim

    def start(self,bundle,local_out,*,runtime_project,manifest_path):
        self.validate_current_admission()
        bundle = Path(bundle).resolve(); local_out = Path(local_out).resolve(); job = os.environ.get('SLURM_JOB_ID')
        if not job or job == self.old_job or bundle == self.bundle or bundle.parent != self.wave.parent/'actor-bundles':
            raise ValueError('New allocated worker and distinct bundle required')
        plan = json.loads(regular_bytes(bundle/'plan.json')); binding = plan[self.binding_name]
        if json.loads(pinned(binding['path'],binding['sha256'])) != self.spec or plan['waves'] != [self.claim]:
            raise ValueError('Exact repair authority and original claim required')
        if not local_out.is_dir() or local_out.is_symlink() or any(local_out.iterdir()):
            raise ValueError('Empty isolated output required')
        from .native_runtime_assets import preflight
        assets = preflight(runtime_project,self.contracts,manifest_path=manifest_path)
        self.lease = self.wave/'first-actor-claim'/self.lease_name; self.lease.mkdir(mode=0o700)
        rec = dict(version=self.version,job=job,old_job=self.old_job,pid=os.getpid(),bundle=str(bundle),
                   local_out=str(local_out),shared_out=self.spec['new_shared_out'],automatic_retry=False)
        atomic_write_json(self.lease/'lease.json',rec)
        self.lease_digest = digest(self.lease/'lease.json'); self.local_out = local_out
        atomic_write_json(bundle/'continuation-start.json',dict(lease=rec,assets=assets))
        return rec

    def begin_source(self,contract,directory):
        task = contract['task_id']; directory = Path(directory).resolve()
        if self.lease is None or digest(self.lease/'lease.json') != self.lease_digest:
            raise ValueError('Exclusive hardware repair lease required')
        lease = json.loads(regular_bytes(self.lease/'lease.json'))
        if lease['pid'] != os.getpid() or lease['job'] != os.environ.get('SLURM_JOB_ID'):
            raise ValueError('Only live lease owner may retry')
        if task in self.started or directory != self.local_out/task or self.contracts[len(self.started)] != contract or any(directory.iterdir()):
            raise ValueError('One ordered unchanged source per explicit repair')
        self.verify_origin()
        # Unlike initialization-only continuation, this is an explicit new runtime attempt.
        with (directory/'attempt-started.json').open('xb') as f:
            f.write(json.dumps(dict(job=lease['job'],task=task,scripted=False)).encode())
        atomic_write_json(directory/(self.lease_name+'.json'),dict(version=self.version,old_job=self.old_job,
            current_job=lease['job'],old_attempt_sha256=hashlib.sha256(self.old_claim_bytes[task]).hexdigest() if self.old_claim_bytes[task] else None,
            prior_attempt_started=bool(self.old_claim_bytes[task]),actor_failure_retry=False,
            runtime_failure_retry=bool(self.old_claim_bytes[task])))
        self.started.append(task)
