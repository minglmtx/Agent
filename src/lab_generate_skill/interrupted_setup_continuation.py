"""Resume an externally terminated, archived site startup before model loading."""
import ast
import hashlib
import json
from lab_generate_skill.slurm_allocation_identity import allocation_tmpdir_matches
from pathlib import Path
from .hardware_failure_continuation import HardwareFailureContinuation
from .initialization_continuation import pinned, digest, regular_bytes, archive_bytes

VERSION='closed-site-startup-interruption-v1'
LEASE='site-startup-continuation-1'
BINDING='interrupted_setup_continuation'
GLOBAL={'executed-code.json','pre-inference-assets.json','pre-inference-browser-config.json','scope.json'}


def verify_interrupted_startup(raw,runner,task,job,diagnostic):
    expected=GLOBAL|{task+'/attempt-started.json'}
    if set(raw)!=expected:
        raise ValueError('Complete archive must contain only startup metadata and first source claim')
    claim=json.loads(raw[task+'/attempt-started.json'])
    if claim!={'job':job,'task':task,'scripted':False}:
        raise ValueError('Exact original first attempt required')
    if diagnostic.get('type')!='SystemExit' or diagnostic.get('stage')!='site_actor_bundle':
        raise ValueError('Actual externally interrupted startup stack required')
    frames=diagnostic.get('frames',[])
    roots=[f for f in frames if f.get('file')=='run_site_navigation_once.py' and f.get('function')=='main']
    if len(roots)!=1 or not any(f.get('file')=='site_worker.py' and f.get('function')=='episode' for f in frames):
        raise ValueError('Interrupted native website episode frame required')
    main=next(n for n in ast.parse(runner).body if isinstance(n,ast.FunctionDef)and n.name=='main')
    calls=[n for n in ast.walk(main)if isinstance(n,ast.Call)]
    entry=[n for n in calls if ast.unparse(n.func)=='sites.episode' and n.lineno==roots[0]['line']]
    loads=[n.lineno for n in calls if ast.unparse(n.func)in {'backend_holder.acquire','load_backend','factory','TransformersChatBackend'}]
    if len(entry)!=1 or not loads or roots[0]['line']>=min(loads):
        raise ValueError('Native startup must precede every recorded model-load path')
    execution=json.loads(raw['executed-code.json'])
    matches=[v for p,v in execution['files'].items()if p.endswith('/scripts/run_site_navigation_once.py')]
    if execution.get('job_id')!=job or matches!=[hashlib.sha256(runner).hexdigest()]:
        raise ValueError('Actually executed frozen runner differs')
    scope=json.loads(raw['scope.json'])
    assets=json.loads(raw['pre-inference-assets.json'])
    browser=json.loads(raw['pre-inference-browser-config.json'])
    if (scope.get('api_calls')!=0 or scope.get('scripted')is not False
            or assets.get('ready')is not True or assets.get('actor_attempts')!=0 or assets.get('api_calls')!=0
            or browser.get('status')!='passed' or browser.get('actor_attempts')!=0 or browser.get('api_calls')!=0):
        raise ValueError('Only real pre-inference setup metadata qualifies')
    return claim


class InterruptedSetupContinuation(HardwareFailureContinuation):
    version=VERSION
    lease_name=LEASE
    binding_name=BINDING

    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('api_calls')!=0:
            raise ValueError('Explicit startup continuation spec required')
        wave=Path(s['wave']).resolve();bundle=Path(s['old_bundle']).resolve();job=s['old_job']
        if self.terminal_query(job).get(job)not in {'FAILED','CANCELLED','TIMEOUT','NODE_FAIL','PREEMPTED'}:
            raise ValueError('Old exact interrupted allocation must be terminal')
        expected={'claim':wave/'first-actor-claim/preflight.json','plan':bundle/'plan.json','state':bundle/'worker-state.json',
                  'local':bundle/'local-output-state.json','closure':bundle/'actor-storage-exit.json'}
        if bundle.parent!=wave.parent/'actor-bundles' or set(s['pins'])!=set(expected) or any(Path(s['pins'][k]['path']).resolve()!=v for k,v in expected.items()):
            raise ValueError('Actual original bundle paths required')
        rows={k:json.loads(pinned(v['path'],v['sha256']))for k,v in s['pins'].items()}
        claim,plan,state,local,closure=(rows[k]for k in ('claim','plan','state','local','closure'))
        if (plan['waves']!=[claim] or claim['wave']!=str(wave) or plan.get('api_calls')!=0
                or state.get('status')!='interrupted_or_failed' or state.get('completed_waves')!=[]
                or state.get('api_calls')!=0 or local.get('services_closed')is not True
                or local.get('bundle')!=str(bundle) or local.get('plan_sha256')!=s['pins']['plan']['sha256']
                or set(local['waves'])!={str(wave)} or local['waves'][str(wave)]['status']!='runner_closed'
                or closure.get('owned_writers_quiet')is not True or closure.get('cleanup_error')is not None
                or closure.get('runner_exit_code')!=143 or closure.get('recovery_status')!='recovered_without_inference'
                or closure.get('recovery_exit_code')!=0 or closure.get('actor_restarted')is not False
                or closure.get('actor_calls_by_recovery')!=0 or closure.get('archive_state')!=str(bundle/'local-output-state.json')
                or not allocation_tmpdir_matches(job, closure['retained_node_local_tmpdir'])):
            raise ValueError('Closed original interrupted worker and complete no-inference recovery required')
        for key,path in [('manifest',Path(claim['manifest'])),('contracts',wave/'contracts.jsonl'),('inventory',wave.parent/'inventory.jsonl')]:
            if digest(path)!=claim[key+'_sha256']:raise ValueError('Original task or split changed')
        self.contracts=[json.loads(line)for line in regular_bytes(claim['manifest']).decode().splitlines()]
        sources=[c['task_id']for c in self.contracts]
        if not 1<=len(sources)<=32 or len(set(sources))!=len(sources) or s['sources']!=sources:
            raise ValueError('All ordered original sources required')
        for proof in claim['proofs']:pinned(proof['file'],proof['sha256'])
        archive=s['archive'];raw=archive_bytes(archive['path'],archive['sha256'],archive['index'],archive['index_sha256'])
        if Path(archive['path'])!=wave/'actor/0/diagnostic-data.tar.gz' or Path(archive['index'])!=wave/'actor/0/diagnostic-members.json':
            raise ValueError('Original complete wave archive required')
        code=archive_bytes(s['runtime']['path'],s['runtime']['sha256']);runner=code[s['runtime']['runner_member']]
        verify_interrupted_startup(raw,runner,sources[0],job,state['diagnostic'])
        if json.loads(raw['executed-code.json'])['manifest_sha256']!=claim['manifest_sha256']:
            raise ValueError('Executed task manifest changed')
        pers=local['persistence'][str(wave)];tasks=pers['tasks']
        if (pers.get('full_output_not_sampled')is not True or pers.get('actor_calls_by_archive')!=0
                or pers.get('archive_sha256')!=archive['sha256'] or pers.get('member_count')!=len(raw)
                or [t['task_id']for t in tasks]!=sources
                or [t['status']for t in tasks]!=['started_not_completed']+['not_started']*(len(sources)-1)
                or any(t.get('first_completed_generation_member')is not None or t.get('copied_raw_members')!=[] for t in tasks)):
            raise ValueError('Exact complete started/unstarted coverage required')
        marker=wave/'actor/0'/sources[0]/'attempt-archive.json';m=json.loads(regular_bytes(marker))
        if m.get('archive_sha256')!=archive['sha256'] or m.get('first_completed_generation_member')is not None or m.get('raw_member_count')!=1:
            raise ValueError('Only the interrupted first claim may exist')
        self.allowed_old_artifacts={marker.resolve():digest(marker)}
        if s['retained_artifacts']!={str(k):v for k,v in self.allowed_old_artifacts.items()} or s['new_shared_out']!=str(wave/'actor'/LEASE):
            raise ValueError('Retained artifacts or separate output changed')
        if (wave/'first-actor-claim'/LEASE).exists()and self.lease is None:raise ValueError('Startup continuation already claimed')
        self.old_claim_bytes={sources[0]:raw[sources[0]+'/attempt-started.json']}
        # Unstarted sources have no previous attempt; keep that distinction.
        self.old_claim_bytes.update({task:b'' for task in sources[1:]})
        self.wave,self.bundle,self.claim,self.old_job=wave,bundle,claim,job
        self.sources=sources
        return claim
