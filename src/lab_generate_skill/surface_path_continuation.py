"""Single-source continuation of the archived private-reference path failure.

The other four original sources, including completed business failures, cannot
use this authority. Original claims and raw archives remain immutable. No
inference or new first-Actor claim occurs during validation.
"""
import ast
from copy import deepcopy
import hashlib,json,os,tarfile
from pathlib import Path
from .hardware_failure_continuation import HardwareFailureContinuation
from .initialization_continuation import pinned,digest,regular_bytes,archive_bytes
from .reset_failure_continuation import selected_claim

SOURCE='78e26845a858ef34bdc1'
TASK=SOURCE+'--native-surface-training-v1'
OLD_JOB='4606606'
VERSION='closed-surface-reference-path-zero-inference-v1'
LEASE='surface-reference-path-1'
BINDING='surface_path_continuation'
OTHER_BINDINGS=('unstarted_continuation','preinference_continuation','hardware_repair_continuation','interrupted_setup_continuation','reset_failure_continuation','unattempted_subset_continuation','terminal_capture_continuation')
REPAIR_FILES={'scripts/run_archived_site_actor_bundle.py','scripts/run_site_actor_bundle.py','scripts/unstarted_actor_continuation.py','src/lab_generate_skill/initialization_continuation.py','src/lab_generate_skill/surface_path_continuation.py'}
FRAMES=[('run_site_navigation_once.py','main'),('runtime_hooks.py','prepare'),('controls.py','prepare_references'),('collect.py','collect'),('collect.py','reverse_context'),('reverse.py','replay_capture'),('map_named_facts_binding.py','require_reverse_body')]
MEMBERS={'attempt-started.json','result.json','source-references/geographic/'+SOURCE+'/reference-0/capture/native-reverse-0.xml','source-references/geographic/'+SOURCE+'/reference-0/capture/native-reverse-0.xml.receipt.json','source-references/geographic/'+SOURCE+'/reference-0/capture/surface-observations.json','source-references/geographic/'+SOURCE+'/reference-0/reference.json','source-references/geographic/result.json','source-references/guard-before.json','source-references/result.json','surface-runtime-binding.json'}


def read_pin(ref):return json.loads(pinned(ref['path'],ref['sha256']))


def zero_request_path_failure(raw,code):
    if set(raw)!=MEMBERS:raise ValueError('Exact complete ten-member pre-request failure archive required')
    claim=json.loads(raw['attempt-started.json']);result=json.loads(raw['result.json'])
    if claim!=dict(job=OLD_JOB,task=TASK,scripted=False):raise ValueError('Original first attempt differs')
    if (result.get('task_id')!=TASK or result.get('domain')!='map' or result.get('status')!='runtime_or_contract_error' or result.get('evaluation')!=dict(status='unknown',reward=None) or result.get('rollout_saved')is not False or result.get('eligible_training_sample')is not False or result.get('api_calls')!=0):raise ValueError('Only the exact closed unknown pre-request result may continue')
    diagnostic=result.get('diagnostic',{});frames=diagnostic.get('frames',[])
    if diagnostic.get('type')!='ValueError' or diagnostic.get('stage')!='site_navigation_attempt' or [(f.get('file'),f.get('function'))for f in frames]!=FRAMES:raise ValueError('Actual private reverse-body failure stack required')
    tree=ast.parse(code['scripts/run_site_navigation_once.py']);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main');calls=[n for n in ast.walk(main)if isinstance(n,ast.Call)]
    failed=[n for n in calls if n.lineno==frames[0]['line']]
    loads=[n.lineno for n in calls if ast.unparse(n.func)in ('load_backend','factory','configure_actor')or isinstance(n.func,ast.Attribute)and n.func.attr in ('acquire','from_pretrained','generate','infer','chat','complete','_load')]
    if len(failed)!=1 or ast.unparse(failed[0].func)!='native_read_hooks.prepare' or not loads or frames[0]['line']>=min(loads):raise ValueError('Frozen exception must precede model acquisition')
    bindings={'runtime_hooks.py':'scripts/map_surfaces/runtime_hooks.py','controls.py':'scripts/map_surfaces/controls.py','collect.py':'scripts/map_surfaces/collect.py','reverse.py':'scripts/map_surfaces/reverse.py','map_named_facts_binding.py':'src/lab_generate_skill/map_named_facts_binding.py'}
    for f in frames[1:]:
        tree=ast.parse(code[bindings[f['file']]])
        functions=[n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name==f['function'] and n.lineno<=f['line']<=n.end_lineno]
        if len(functions)!=1:raise ValueError('Actual frozen native exception frame differs')
    guard=code['src/lab_generate_skill/map_named_facts_binding.py'].decode()
    line=guard.splitlines()[frames[-1]['line']-1]
    if 'raise ValueError'not in line or 'private'not in line.lower():raise ValueError('Exact private reference guard required')
    binding=json.loads(raw['surface-runtime-binding.json'])
    if binding.get('reference_verified')is not False or binding.get('actor_actions_created')!=0 or binding.get('private_reference_added_to_observation')is not False or binding.get('errors')!=[dict(stage='prepare',type='ValueError',message='Independent actual private reverse references unavailable')]:raise ValueError('Current archived binding contradicts preparation failure')
    return claim


class SurfacePathContinuation(HardwareFailureContinuation):
    version=VERSION
    lease_name=LEASE
    binding_name=BINDING

    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('source_task_id')!=SOURCE or s.get('sources')!=[TASK] or s.get('old_job')!=OLD_JOB or s.get('api_calls')!=0 or s.get('old_model_requests')!=0:raise ValueError('Only the declared single zero-request source may continue')
        if self.terminal_query(OLD_JOB)!={OLD_JOB:'COMPLETED'}:raise ValueError('Original allocation must be completed')
        origin=Path(s['origin']).resolve();base=origin/'progress';wave=base/'plain3';bundle=base/'actor-bundles/surfaces5'
        if origin.name!='surfaces-first-actor-v175' or Path(s['wave']).resolve()!=wave or Path(s['old_bundle']).resolve()!=bundle:raise ValueError('Exact original multiwave producer paths required')
        expected={'submitted':origin/'submitted.json','producer':origin/'plan.json','claim':wave/'first-actor-claim/preflight.json','plan':bundle/'plan.json','state':bundle/'worker-state.json','local':bundle/'local-output-state.json','claimed':bundle/'claimed-waves.json','termination':origin/'termination.json','leases':origin/'actor-source-history/source-leases.json','review':origin.parent/'surfaces-actor-independent-review-v175/independent-review.json'}
        if set(s['pins'])!=set(expected)or any(Path(s['pins'][k]['path']).resolve()!=p for k,p in expected.items()):raise ValueError('Complete canonical original metadata pins required')
        rows={k:read_pin(ref)for k,ref in s['pins'].items()};plan=rows['plan'];original=rows['claim'];local=rows['local'];state=rows['state'];review=rows['review']
        if (rows['submitted'].get('job_id')!=OLD_JOB or rows['submitted'].get('plan')!=s['pins']['producer'] or plan.get('base')!=str(base)or plan.get('domain')!='map'or plan.get('tasks')!=5 or plan.get('api_calls')!=0 or len(plan.get('waves',[]))!=2 or plan['waves'][0]!=original or rows['claimed']!=plan['waves']):raise ValueError('Original five-source two-wave first claim differs')
        if (state.get('status')!='completed'or state.get('api_calls')!=0 or state.get('completed_waves')!=[dict(wave=w['wave'],tasks=w['tasks'],result_records=w['tasks'])for w in plan['waves']]or local.get('services_closed')is not True or local.get('bundle')!=str(bundle)or local.get('plan_sha256')!=s['pins']['plan']['sha256']or set(local['waves'])!={w['wave']for w in plan['waves']}or any(x['status']!='runner_closed'for x in local['waves'].values())):raise ValueError('All original source workers and services must be closed')
        termination=rows['termination']
        if termination.get('confirmed')is not True or termination.get('returncode')!=0 or termination.get('group',{}).get('live_members')!=[] or termination.get('scope',{}).get('live_scratch_references')!=[] or termination.get('scope',{}).get('unreadable_same_uid_pids')!=[]:raise ValueError('Original process groups and scratch writers must be quiet')
        if (review.get('passed')is not True or review.get('actor_job')!=OLD_JOB or review.get('plan')!=s['pins']['producer']or review.get('capsule')!=rows['producer']['capsule']or review.get('termination')!=s['pins']['termination']or review.get('source_leases')!=s['pins']['leases']or review.get('full_partition_coverage_verified')is not True or review.get('requests_reconstructed')!=4):raise ValueError('Independent complete original execution review required')
        if self.terminal_query(review['reader_job'])!={review['reader_job']:'COMPLETED'}:raise ValueError('Independent zero-request reader must be completed')
        reviewed=review['sources']+review['unknown_sources'];selected=[r for r in reviewed if r['source_task_id']==SOURCE]
        if len(reviewed)!=5 or len({r['source_task_id']for r in reviewed})!=5 or len(selected)!=1:raise ValueError('All original five sources must remain represented')
        target=selected[0]
        if target.get('zero_inference_verified')is not True or target.get('model_requests')!=0 or target.get('status')!='unknown' or target.get('reward')is not None or target.get('diagnosis')!='private_reference_path_rejection_before_model_request':raise ValueError('Selected source is not the verified pre-request path failure')
        if set(s['wave_indexes'])!={w['wave']for w in plan['waves']} or any(Path(s['wave_indexes'][w['wave']]['path']).resolve()!=Path(w['wave'])/'actor/0/diagnostic-members.json'for w in plan['waves']):raise ValueError('Both original complete wave indexes must remain pinned')
        all_contracts=[];siblings={}
        for w in plan['waves']:
            wp=Path(w['wave'])
            if wp.parent!=base or digest(w['manifest'])!=w['manifest_sha256']or digest(wp/'contracts.jsonl')!=w['contracts_sha256']or digest(base/'inventory.jsonl')!=w['inventory_sha256']:raise ValueError('Original manifest, public contract or inventory drift')
            for proof in w['proofs']:pinned(proof['file'],proof['sha256'])
            contracts=[json.loads(line)for line in regular_bytes(w['manifest']).decode().splitlines()];all_contracts.extend(contracts)
            for c in contracts:
                if c['task_id']!=TASK:siblings[c['task_id']]=wp/'actor/0'/c['task_id']/'result.json'
            index=read_pin(s['wave_indexes'][w['wave']]);merged={}
            if index.get('full_output_not_sampled')is not True:raise ValueError('Complete raw wave partition required')
            for part in index['parts']:
                pinned(part['archive'],part['archive_sha256']);part_index=json.loads(pinned(part['manifest'],part['manifest_sha256']))
                for name,ref in part_index['members'].items():
                    full=part['prefix']+'/'+name if part['prefix']else name
                    if full in merged:raise ValueError('Duplicate original wave member')
                    merged[full]=ref
            if merged!=index['members']or len(merged)!=index['member_count']:raise ValueError('Original wave partition coverage differs')
        if len(all_contracts)!=5 or {c['source_task_id']for c in all_contracts}!={r['source_task_id']for r in reviewed}:raise ValueError('Original source coverage differs from independent review')
        if set(s['sibling_results'])!=set(siblings)or any(Path(s['sibling_results'][k]['path']).resolve()!=p for k,p in siblings.items()):raise ValueError('All four unselected sibling results must stay pinned')
        for ref in s['sibling_results'].values():read_pin(ref)
        leases=rows['leases']
        if leases.get('state')!='acquired'or leases.get('closed')is not True or leases.get('claims_released')is not False or leases.get('process',{}).get('job_id')!=OLD_JOB or leases.get('original_inventory',{}).get('sha256')!=original['inventory_sha256']:raise ValueError('Retain all original source-exclusive claims')
        for ref in leases['claims'].values():read_pin(ref)
        if SOURCE not in leases['claims']:raise ValueError('Selected original source lease missing')
        cap=read_pin(rows['producer']['capsule']);pinned(cap['archive'],cap['archive_sha256']);wanted={'scripts/run_site_navigation_once.py','scripts/run_archived_site_actor_bundle.py','scripts/map_surfaces/runtime_hooks.py','scripts/map_surfaces/controls.py','scripts/map_surfaces/collect.py','scripts/map_surfaces/reverse.py','src/lab_generate_skill/map_named_facts_binding.py'};code={}
        with tarfile.open(cap['archive'])as t:
            for name in wanted:
                member=t.getmember(name)
                if not member.isfile():raise ValueError('Regular original executed code required')
                raw=t.extractfile(member).read();ref=cap['members'][name]
                if dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())!=ref:raise ValueError('Original frozen executable differs')
                code[name]=raw
        if s['archive']!=target['archive']or s['archive_index']!=target['manifest']:raise ValueError('Actual independently reviewed target archive required')
        raw=archive_bytes(s['archive']['path'],s['archive']['sha256'],s['archive_index']['path'],s['archive_index']['sha256']);zero_request_path_failure(raw,code)
        self.old_claim_bytes={TASK:raw['attempt-started.json']};marker=wave/'actor/0'/TASK/'attempt-archive.json';m=json.loads(regular_bytes(marker));index_ref=s['wave_indexes'][str(wave)]
        if m.get('archive_path')!=s['archive']['path']or m.get('archive_sha256')!=s['archive']['sha256']or m.get('raw_member_count')!=len(raw)or m.get('first_completed_generation_member')is not None or m.get('automatic_retry')is not False or m.get('partition_index_sha256')!=index_ref['sha256']:raise ValueError('Original complete target archive marker differs')
        result=wave/'actor/0'/TASK/'result.json'
        if regular_bytes(result)!=raw['result.json']:raise ValueError('Retained original failure differs from raw archive')
        self.allowed_old_artifacts={p.resolve():digest(p)for p in (marker,result)}
        if s['retained_artifacts']!={str(k):v for k,v in self.allowed_old_artifacts.items()}:raise ValueError('Only exact retained original target artifacts may be exempted')
        manifest=Path(s['subset_manifest']).resolve()
        if manifest.parent!=wave or manifest in (Path(original['manifest']),wave/'contracts.jsonl'):raise ValueError('Separate immutable original-wave subset manifest required')
        claim,contracts=selected_claim(original,[c for c in all_contracts if c['task_id']in {p['task_id']for p in original['proofs']}],manifest,[TASK])
        if contracts[0].get('source_task_id')!=SOURCE:raise ValueError('Original source identity changed')
        repair=read_pin(s['repair_review'])
        if (repair.get('passed')is not True or repair.get('source_task_id')!=SOURCE or repair.get('actual_archive')!=s['archive']or repair.get('actual_manifest')!=s['archive_index']or not all(repair.get(k)is True for k in ('raw_failure_reproduced','identical_raw_capture_passed_neutral_path','private_reference_guard_unchanged','legacy_node_local_layout_readable','shared_archive_paths_unchanged','public_input_and_native_evaluator_unchanged'))):raise ValueError('Narrow observed path repair review required')
        if hashlib.sha256(code['scripts/run_archived_site_actor_bundle.py']).hexdigest()!=repair['original']['sha256']:raise ValueError('Repair does not originate in the executed wrapper')
        pinned(repair['candidate']['path'],repair['candidate']['sha256'])
        if set(s['repair_runtime_pins'])!=REPAIR_FILES or s['repair_runtime_pins']['scripts/run_archived_site_actor_bundle.py']['sha256']!=repair['candidate']['sha256']:raise ValueError('Exact minimal path repair and scoped entry modules required')
        for ref in s['repair_runtime_pins'].values():pinned(ref['path'],ref['sha256'])
        if s['new_shared_out']!=str(wave/'actor'/LEASE):raise ValueError('Dedicated continuation output required')
        if (wave/'first-actor-claim'/LEASE).exists()and self.lease is None:raise ValueError('This continuation is already claimed')
        self.wave,self.bundle,self.claim,self.old_job=wave,bundle,claim,OLD_JOB
        self.contracts,self.sources=contracts,[TASK]
        return claim

    def start(self,bundle,local_out,*,runtime_project,manifest_path):
        if 'runtime_review'not in self.spec:raise ValueError('Independent repaired-runtime admission review required before execution')
        review=read_pin(self.spec['runtime_review'])
        origin_spec={k:v for k,v in self.spec.items()if k!='runtime_review'}
        identity=hashlib.sha256(json.dumps(origin_spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if (review.get('version')!='surface78-current-runtime-preflight-v1' or review.get('passed')is not True or review.get('source_task_id')!=SOURCE or review.get('origin_spec_sha256')!=identity or review.get('zero_request_origin_verified')is not True or review.get('old_registered_sources_verified')!=1955 or review.get('ordinary_source_admission_verified')is not True or review.get('model_inference_calls')!=0):raise ValueError('Complete current-runtime/source verification must bind this exact origin and repair')
        if self.terminal_query(review['reader_job'])!={review['reader_job']:'COMPLETED'}:raise ValueError('Repaired-runtime reader is not confirmed complete')
        cap=read_pin(review['capsule'])
        for name,ref in cap['members'].items():
            if Path(name).is_absolute()or '..'in Path(name).parts or digest(Path(runtime_project)/name)!=ref['sha256']:raise ValueError('Actual complete executing capsule differs from independently verified runtime')
        for name,ref in self.spec['repair_runtime_pins'].items():
            if digest(Path(runtime_project)/name)!=ref['sha256']:raise ValueError('Executing continuation code differs from reviewed candidate')
        if Path(__file__).resolve()!=Path(runtime_project).resolve()/'src/lab_generate_skill/surface_path_continuation.py':raise ValueError('Continuation authority imported outside executing project')
        return super().start(bundle,local_out,runtime_project=runtime_project,manifest_path=manifest_path)
