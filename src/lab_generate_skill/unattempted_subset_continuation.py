"""Continue untouched siblings of a watchdog-stopped batch, never retry its task.

The old claim, raw archive and supervisor diagnostic remain pinned. The ordinary
source, heldout, alias and full-admission guards still run. The new exclusive
lease selects only sources with no old artifact, including partial generations.
"""
import json
from lab_generate_skill.slurm_allocation_identity import allocation_tmpdir_matches
from pathlib import Path
from .hardware_failure_continuation import HardwareFailureContinuation
from .initialization_continuation import pinned, digest, regular_bytes, archive_bytes

VERSION='watchdog-unattempted-source-subset-v1'
BINDING='unattempted_subset_continuation'
LEASE='unattempted-subset-1'


def require_untouched(raw, contracts, requested, watchdog):
    ids=sorted(c['task_id'] for c in contracts)
    if not requested or requested!=sorted(set(requested)) or not set(requested)<=set(ids):
        raise ValueError('Unique ordered original source subset required')
    stopped=watchdog.get('task_id')
    if (stopped not in ids or stopped in requested
            or watchdog.get('evaluation')!={'status':'unknown','reward':None}
            or watchdog.get('watchdog',{}).get('enforcement')!='independent_process_group_termination'):
        raise ValueError('An actual supervisor-stopped sibling, never the selected task, is required')
    # The ordinary runner visits sources in task-ID order. Do not use a missing
    # archive entry to infer an earlier task never ran.
    if any(t<=stopped for t in requested):
        raise ValueError('Only tasks after the interrupted source may continue')
    for task in requested:
        if any(name==task or name.startswith(task+'/') for name in raw):
            raise ValueError('Any original task artifact prevents an unattempted continuation')
    if not any(n.startswith(stopped+'/generation-') for n in raw):
        raise ValueError('Retained original interrupted model work required')
    return [c for c in sorted(contracts,key=lambda c:c['task_id']) if c['task_id'] in requested]


class UnattemptedSubsetContinuation(HardwareFailureContinuation):
    version=VERSION
    binding_name=BINDING
    lease_name=LEASE

    def select_sources(self, raw, contracts, requested, watchdog):
        return require_untouched(raw,contracts,requested,watchdog)

    def retain_original_artifacts(self, raw, selected):
        self.old_claim_bytes={c['task_id']:b'' for c in selected}
        self.allowed_old_artifacts={}

    def verify_origin(self):
        s=self.spec
        if s.get('version')!=self.version or s.get('api_calls')!=0:
            raise ValueError('Explicit untouched-subset authority required')
        wave=Path(s['wave']).resolve();bundle=Path(s['old_bundle']).resolve();job=s['old_job']
        if self.terminal_query(job)!={job:'FAILED'}:
            raise ValueError('Original exact watchdog allocation must be terminal FAILED')
        expected={'claim':wave/'first-actor-claim/preflight.json','plan':bundle/'plan.json',
                  'local':bundle/'local-output-state.json','closure':bundle/'actor-storage-exit.json',
                  'watchdog':bundle/'watchdog.timeout.json'}
        if set(s['pins'])!=set(expected) or any(Path(s['pins'][k]['path']).resolve()!=p for k,p in expected.items()):
            raise ValueError('Exact original producer paths required')
        docs={k:json.loads(pinned(v['path'],v['sha256'])) for k,v in s['pins'].items()}
        original,plan,local,closure,watchdog=(docs[k] for k in ('claim','plan','local','closure','watchdog'))
        if (bundle.parent!=wave.parent/'actor-bundles' or plan['waves']!=[original]
                or original['wave']!=str(wave) or plan.get('api_calls')!=0
                or local.get('bundle')!=str(bundle) or local.get('plan_sha256')!=s['pins']['plan']['sha256']
                or set(local['waves'])!={str(wave)} or local['waves'][str(wave)]['status']!='runner_closed'
                or closure.get('runner_exit_code')!=124 or closure.get('owned_writers_quiet') is not True
                or closure.get('subreaper_enabled') is not True or closure.get('cleanup_error') is not None
                or closure.get('actor_restarted') is not False or closure.get('actor_calls_by_recovery')!=0
                or closure.get('archive_state')!=str(bundle/'local-output-state.json')
                or not allocation_tmpdir_matches(job, closure['retained_node_local_tmpdir'])
                or watchdog.get('watchdog',{}).get('pid')!=local['pid']):
            raise ValueError('Pinned normal worker and quiescent supervisor closure required')
        for key,path in [('manifest',Path(original['manifest'])),('contracts',wave/'contracts.jsonl'),('inventory',wave.parent/'inventory.jsonl')]:
            if digest(path)!=original[key+'_sha256']:raise ValueError('Original task/proof/split changed')
        contracts=[json.loads(x) for x in regular_bytes(original['manifest']).decode().splitlines()]
        rec=s['raw']
        if Path(rec['archive'])!=wave/'actor/0/diagnostic-data.tar.gz' or Path(rec['index'])!=wave/'actor/0/diagnostic-members.json':
            raise ValueError('Exact original full wave archive required')
        raw=archive_bytes(rec['archive'],rec['archive_sha256'],rec['index'],rec['index_sha256'])
        selected=self.select_sources(raw,contracts,s['task_ids'],watchdog)
        manifest=Path(s['manifest']['path'])
        if manifest.parent!=wave or manifest.name in ('contracts.jsonl','admitted.jsonl'):
            raise ValueError('Separate exact subset manifest inside original wave required')
        actual=[json.loads(x) for x in pinned(manifest,s['manifest']['sha256']).decode().splitlines()]
        if actual!=selected:raise ValueError('Subset changed original task/proof')
        by_id={p['task_id']:p for p in original['proofs']}
        claim={**original,'manifest':str(manifest),'manifest_sha256':s['manifest']['sha256'],
               'tasks':len(selected),'proofs':[by_id[c['task_id']] for c in selected]}
        for proof in claim['proofs']:pinned(proof['file'],proof['sha256'])
        if s['new_shared_out']!=str(wave/'actor'/self.lease_name):raise ValueError('Separate continuation output required')
        if (wave/'first-actor-claim'/self.lease_name).exists() and self.lease is None:
            raise ValueError('Untouched subset is already leased')
        self.wave,self.bundle,self.claim,self.old_job=wave,bundle,claim,job
        self.contracts=selected;self.sources=s['task_ids']
        self.retain_original_artifacts(raw,selected)
        return claim
