"""Continue only a closed reset-failure subset; never retry scored siblings.

The original claim, manifest, completed siblings and archived zero-generation
failure remain immutable. The selected subset has its own exclusive lease and
uses unchanged tasks/proofs plus the normal source, split and alias guards.
"""
import json
import re
from copy import deepcopy
from pathlib import Path
from .hardware_failure_continuation import HardwareFailureContinuation
from .initialization_continuation import pinned, digest, regular_bytes, archive_bytes

VERSION='closed-reset-zero-generation-subset-v1'
BINDING='reset_failure_continuation'
LEASE='reset-zero-generation-1'


def verify_reset_failure(raw, task, job):
    forbidden=re.compile(r'^(generation|partial[-_]generation|actor[-_]input|actor[-_]output|step[-_]|inference[-_]started)',re.I)
    if any(forbidden.match(Path(n).name)for n in raw):
        raise ValueError('Generation or action evidence prohibits reset continuation')
    claim=json.loads(raw['attempt-started.json']);r=json.loads(raw['result.json'])
    if claim!={'job':job,'task':task,'scripted':False}:
        raise ValueError('Exact original attempt required')
    if (r.get('task_id')!=task or r.get('rounds')!=0 or r.get('actor_attempts')!=0
            or r.get('api_calls')!=0 or r.get('finish_reason')!='runtime_error'
            or r.get('evaluation',{}).get('status')!='unknown'
            or r['evaluation'].get('reward') is not None
            or r.get('error',{}).get('stage')!='environment_reset'
            or r['error'].get('type')!='TimeoutError'):
        raise ValueError('Only actual zero-inference reset timeout may continue')
    for name in ('trajectory.json','rollout-raw.json'):
        row=json.loads(raw[name])
        if (row.get('task_id')!=task or row.get('rounds')!=0 or row.get('messages')!=[]
                or row.get('generation_finish_reasons')!=[] or row.get('error')!=r['error']
                or row.get('finish_reason')!='runtime_error'
                or row.get('provenance',{}).get('system_prompt_source')!='no_actor_request'):
            raise ValueError('Full trajectory contradicts zero model requests')
        diagnostics=row.get('task_output',{}).get('runtime_diagnostics',[])
        if not any(d.get('stage')=='environment_reset' and any(
                f.get('file')=='map_native_facts_normal.py' and f.get('function')=='wait_rendered_initial_view'
                for f in d.get('frames',[]))for d in diagnostics):
            raise ValueError('Reviewed native initial-render failure is required')
    return claim


def selected_claim(original, contracts, manifest, requested):
    ids=[c['task_id']for c in contracts]
    if not requested or len(set(requested))!=len(requested) or not set(requested)<=set(ids):
        raise ValueError('Nonempty unique subset of original tasks required')
    selected=[c for c in contracts if c['task_id']in requested]
    if [c['task_id']for c in selected]!=requested:
        raise ValueError('Preserve original source order')
    actual=[json.loads(s)for s in regular_bytes(manifest).decode().splitlines()]
    if actual!=selected:raise ValueError('Subset must retain exact original task and proof bytes')
    claim=deepcopy(original);claim.update(manifest=str(manifest),manifest_sha256=digest(manifest),
        tasks=len(selected),proofs=[p for p in original['proofs']if p['task_id']in requested])
    if len(claim['proofs'])!=len(selected):raise ValueError('Original proofs missing')
    return claim,selected


class ResetFailureContinuation(HardwareFailureContinuation):
    version=VERSION
    lease_name=LEASE
    binding_name=BINDING

    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('api_calls')!=0:
            raise ValueError('Explicit reset repair authority required')
        wave=Path(s['wave']).resolve();bundle=Path(s['old_bundle']).resolve();job=s['old_job']
        if self.terminal_query(job)!={job:'COMPLETED'}:
            raise ValueError('Mixed original batch must be completed and closed')
        expected={'claim':wave/'first-actor-claim/preflight.json','plan':bundle/'plan.json',
                  'state':bundle/'worker-state.json','local':bundle/'local-output-state.json',
                  'closure':bundle/'actor-storage-exit.json'}
        if set(s['pins'])!=set(expected) or any(Path(s['pins'][k]['path']).resolve()!=v for k,v in expected.items()):
            raise ValueError('Original producer paths required')
        rows={k:json.loads(pinned(v['path'],v['sha256']))for k,v in s['pins'].items()}
        original,plan,state,local,closure=(rows[k]for k in ('claim','plan','state','local','closure'))
        if (bundle.parent!=wave.parent/'actor-bundles' or plan['waves']!=[original]
                or original['wave']!=str(wave) or plan.get('api_calls')!=0
                or state.get('status')!='completed' or state.get('api_calls')!=0
                or state.get('completed_waves')!=[dict(wave=str(wave),tasks=original['tasks'],result_records=original['tasks'])]
                or local.get('services_closed') is not True or local.get('bundle')!=str(bundle)
                or local.get('plan_sha256')!=s['pins']['plan']['sha256']
                or set(local['waves'])!={str(wave)} or local['waves'][str(wave)]['status']!='runner_closed'
                or closure.get('owned_writers_quiet')is not True or closure.get('cleanup_error')is not None
                or closure.get('actor_restarted')is not False or closure.get('actor_calls_by_recovery')!=0):
            raise ValueError('Closed original batch, services and writers required')
        for key,path in [('manifest',Path(original['manifest'])),('contracts',wave/'contracts.jsonl'),('inventory',wave.parent/'inventory.jsonl')]:
            if digest(path)!=original[key+'_sha256']:raise ValueError('Original source or split drift')
        for proof in original['proofs']:pinned(proof['file'],proof['sha256'])
        manifest=Path(s['subset_manifest']).resolve()
        if manifest.parent!=wave or manifest in (Path(original['manifest']),wave/'contracts.jsonl'):
            raise ValueError('Separate original-wave subset manifest required')
        contracts=[json.loads(line)for line in regular_bytes(original['manifest']).decode().splitlines()]
        requested=s['sources'];claim,selected=selected_claim(original,contracts,manifest,requested)
        if set(s['tasks'])!=set(requested):raise ValueError('Every selected failure needs complete raw evidence')
        self.allowed_old_artifacts={};self.old_claim_bytes={}
        for task in requested:
            rec=s['tasks'][task]
            raw=archive_bytes(rec['archive'],rec['archive_sha256'],rec['index'],rec['index_sha256'])
            verify_reset_failure(raw,task,job);self.old_claim_bytes[task]=raw['attempt-started.json']
            marker=wave/'actor/0'/task/'attempt-archive.json';m=json.loads(regular_bytes(marker))
            if (m.get('archive_path')!=rec['archive'] or m.get('archive_sha256')!=rec['archive_sha256']
                    or m.get('first_completed_generation_member')is not None or m.get('automatic_retry')is not False):
                raise ValueError('Original full archive binding differs')
            for name in ('result.json','trajectory.json','trajectory.md','terminal-page.json'):
                path=wave/'actor/0'/task/name
                if regular_bytes(path)!=raw[name]:raise ValueError('Retained reset result differs')
                self.allowed_old_artifacts[path.resolve()]=digest(path)
            self.allowed_old_artifacts[marker.resolve()]=digest(marker)
        if s['retained_artifacts']!={str(k):v for k,v in self.allowed_old_artifacts.items()}:
            raise ValueError('Exact retained selected artifacts required')
        # Preserve completed siblings and prevent a stale result being removed
        # to make it look like an unstarted task in a later repair.
        siblings={c['task_id']for c in contracts}-set(requested)
        if set(s['sibling_results'])!=siblings:raise ValueError('All unselected original siblings must remain pinned')
        for task,pin in s['sibling_results'].items():
            if Path(pin['path']).resolve()!=wave/'actor/0'/task/'result.json':raise ValueError('Sibling result path differs')
            pinned(pin['path'],pin['sha256'])
        review=json.loads(pinned(s['repair_review']['path'],s['repair_review']['sha256']))
        if (len(requested)!=1 or review.get('task_id')!=requested[0]
                or review.get('initial_render_and_normal_reset_verified')is not True
                or review.get('actor_attempts')!=0 or review.get('api_calls')!=0
                or review.get('unchanged_original_start')!=selected[0]['start_path']):
            raise ValueError('Independent exact-start initial-render repair review required')
        if self.terminal_query(review['job_id'])!={review['job_id']:'COMPLETED'}:
            raise ValueError('Repair control allocation is not confirmed complete')
        pinned(review['archive'],review['archive_sha256'])
        expected_repair={'scripts/run_site_navigation_once.py',
            'src/lab_generate_skill/map_tile_warmup.py',
            'src/lab_generate_skill/map_native_facts_normal.py',
            'src/lab_generate_skill/map_native_facts_runtime.py'}
        if set(s['repair_runtime_pins'])!=expected_repair:
            raise ValueError('Complete validated initial-render implementation required')
        for relative,pin in s['repair_runtime_pins'].items():
            if Path(relative).is_absolute()or '..'in Path(relative).parts:
                raise ValueError('Relative repaired runtime member required')
            pinned(pin['path'],pin['sha256'])
        if s['new_shared_out']!=str(wave/'actor'/LEASE):raise ValueError('Dedicated continuation output required')
        if (wave/'first-actor-claim'/LEASE).exists()and self.lease is None:
            raise ValueError('Reset continuation already claimed')
        self.wave,self.bundle,self.claim,self.old_job=wave,bundle,claim,job
        self.contracts,self.sources=selected,requested
        return claim

    def start(self,bundle,local_out,*,runtime_project,manifest_path):
        for relative,pin in self.spec['repair_runtime_pins'].items():
            if digest(Path(runtime_project)/relative)!=pin['sha256']:
                raise ValueError('Frozen repair implementation differs from validated code')
        return super().start(bundle,local_out,runtime_project=runtime_project,manifest_path=manifest_path)
