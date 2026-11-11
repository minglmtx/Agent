"""Exclusive continuation of two closed PNG initial-view timeouts with zero requests.

Original first claims, complete error archives and three other outcomes persist.
The existing public initial-viewport readiness function is the only native repair.
"""
import ast,json,hashlib,tarfile
from copy import deepcopy
from pathlib import Path
from .hardware_failure_continuation import HardwareFailureContinuation
from .initialization_continuation import pinned,digest,regular_bytes,archive_bytes
from .reset_failure_continuation import selected_claim
SOURCES=('3163cfbe4a2f0114b45f','50e038cdc546bacdd1b0')
TASKS=tuple(s+'--native-surface-training-v1'for s in SOURCES)
OLD_JOB='4606606'
VERSION='closed-surface-png-zero-request-readiness-v1'
LEASE='surface-png-readiness-1'
BINDING='surface_png_continuation'
OTHER_BINDINGS=('unstarted_continuation','preinference_continuation','hardware_repair_continuation','interrupted_setup_continuation','reset_failure_continuation','unattempted_subset_continuation','terminal_capture_continuation','surface_path_continuation')
REPAIR_FILES={'scripts/run_site_actor_bundle.py','scripts/unstarted_actor_continuation.py','src/lab_generate_skill/initialization_continuation.py','src/lab_generate_skill/surface_png_continuation.py','src/lab_generate_skill/map_tile_warmup.py'}
ORIGINAL_CODE={'scripts/run_site_navigation_once.py','scripts/map_surfaces/runtime_hooks.py','scripts/map_surfaces/png_hooks.py','src/lab_generate_skill/gobrowse_runtime.py','src/lab_generate_skill/rollout_checkpoint.py','scripts/map_surfaces/png_reference.py','src/lab_generate_skill/map_native_facts_normal.py'}
COMMON_MEMBERS={'action-interface.json','actor-budget.json','attempt-started.json','initial-page-health.json','png-initial.json','result.json','rollout-checkpoint.json','rollout-raw.json','source-references/guard-after.json','source-references/guard-before.json','source-references/result.json','surface-runtime-binding.json','terminal-capture-error.json','trajectory.json'}
MEMBERS={SOURCES[0]:COMMON_MEMBERS|{'source-references/geographic/named-0/geometry.body','source-references/geographic/named-0/geometry.receipt.json','source-references/geographic/named-0/search.body','source-references/geographic/named-0/search.receipt.json','source-references/geographic/result.json'},SOURCES[1]:COMMON_MEMBERS|{'png-initial-route/manifest.json','png-initial-route/response-0.json.body'}}
def read_pin(ref):return json.loads(pinned(ref['path'],ref['sha256']))
def zero_request_png_failure(raw,code,sid):
    if sid not in SOURCES or set(raw)!=MEMBERS[sid]:raise ValueError('Exact complete original PNG failure archive required')
    task=TASKS[SOURCES.index(sid)];read=lambda n:json.loads(raw[n]);claim=read('attempt-started.json');result=read('result.json')
    if claim!=dict(job=OLD_JOB,task=task,scripted=False):raise ValueError('Original first PNG attempt differs')
    if result.get('task_id')!=task or result.get('domain')!='map' or result.get('status')!='runtime_or_contract_error'or result.get('evaluation')!=dict(status='unknown',reward=None)or result.get('rollout_saved')is not True or result.get('eligible_training_sample')is not False or result.get('api_calls')!=0:raise ValueError('Only complete unknown zero-request initialization failure may continue')
    traces=[read(n)for n in ('trajectory.json','rollout-raw.json')]
    # The actual frozen checkpoint writer creates an explicitly unscored view.
    # Reproduce only its known metadata transformation; all interaction bytes match.
    from . import rollout_checkpoint
    if ast.dump(ast.parse(code['src/lab_generate_skill/rollout_checkpoint.py']))!=ast.dump(ast.parse(regular_bytes(Path(rollout_checkpoint.__file__).resolve()))):raise ValueError('Original checkpoint transformation changed')
    pending=deepcopy(traces[1]);pending['evaluation_outcome']='unknown';pending['evaluation_feedback']={'status':'pending_terminal_evaluation'};output=pending.setdefault('task_output',{});output['openended_environment_reward']=output.get('reward');output['reward']=None;pending['eligible_training_sample']=False
    if traces[0]!=pending or traces[1].get('task_output',{}).get('reward')is not None:raise ValueError('Retained and raw no-request trajectory differ beyond actual unscored checkpoint metadata')
    trace=traces[0]
    if (trace.get('task_id')!=task or trace.get('rounds')!=0 or trace.get('messages')!=[]or trace.get('generation_finish_reasons')!=[]or trace.get('finish_reason')!='runtime_error'or trace.get('error',{}).get('stage')!='environment_reset'or trace['error'].get('type')!='TimeoutError'or trace.get('provenance',{}).get('system_prompt_source')!='no_actor_request'or trace.get('system_prompt')!=''):raise ValueError('Any actual request, generation, action or different failure prohibits this continuation')
    checkpoint=read('rollout-checkpoint.json')
    if checkpoint!=dict(interaction_complete=True,terminal_evaluation_complete=False,rounds=0,finish_reason='runtime_error',raw_file='rollout-raw.json',api_calls=0):raise ValueError('Original zero-request checkpoint differs')
    initial=read('png-initial.json');errors=initial.get('errors',[]);binding=read('surface-runtime-binding.json')
    if initial.get('initial')is not None or initial.get('actor_context_actions')!=0 or len(errors)!=1 or errors[0].get('type')!='TimeoutError'or errors[0].get('stage')!='initial'or not errors[0].get('message','').startswith('Page.wait_for_function: Timeout '):raise ValueError('Actual first PNG native tile wait failure required')
    if binding.get('reference_verified')is not False or binding.get('actor_actions_created')!=0 or binding.get('private_reference_added_to_observation')is not False or binding.get('errors')!=[dict(stage='initial_reference_binding',type='TimeoutError',message=errors[0]['message'])]:raise ValueError('Private binding must remain unavailable before the first observation')
    frames=result.get('diagnostic',{}).get('frames',[]);expected=[('run_site_navigation_once.py','main'),('runtime_hooks.py','score_terminal'),('png_hooks.py','score_terminal')]
    if result.get('diagnostic',{}).get('type')!='ValueError'or [(f.get('file'),f.get('function'))for f in frames]!=expected:raise ValueError('Exact unscorable terminal after PNG reset failure required')
    bindings={'run_site_navigation_once.py':'scripts/run_site_navigation_once.py','runtime_hooks.py':'scripts/map_surfaces/runtime_hooks.py','png_hooks.py':'scripts/map_surfaces/png_hooks.py'}
    for frame in frames:
        functions=[n for n in ast.walk(ast.parse(code[bindings[frame['file']]]))if isinstance(n,ast.FunctionDef)and n.name==frame['function']and n.lineno<=frame['line']<=n.end_lineno]
        if len(functions)!=1:raise ValueError('Actual frozen exception frame differs')
    diagnostics=trace.get('task_output',{}).get('runtime_diagnostics',[])
    if len(diagnostics)!=2 or diagnostics[0].get('stage')!='environment_reset'or diagnostics[0].get('type')!='TimeoutError'or diagnostics[0].get('api')!='Page.wait_for_function':raise ValueError('Original native initial-view timeout diagnostic required')
    initial_frames=diagnostics[0]['frames'][1:6];expected_initial=[('run_site_navigation_once.py','setup'),('runtime_hooks.py','observe_initial'),('png_hooks.py','observe_initial'),('png_reference.py','observe_initial'),('map_native_facts_normal.py','wait_rendered_initial_view')]
    if [(f.get('file'),f.get('function'))for f in initial_frames]!=expected_initial:raise ValueError('Original native initial tile wait frame chain required')
    bindings.update({'png_reference.py':'scripts/map_surfaces/png_reference.py','map_native_facts_normal.py':'src/lab_generate_skill/map_native_facts_normal.py'})
    for frame in initial_frames:
        tree=ast.parse(code[bindings[frame['file']]])
        if len([n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name==frame['function']and n.lineno<=frame['line']<=n.end_lineno])!=1:raise ValueError('Original initial-view exception frame differs')
    last=initial_frames[-1];calls=[n for n in ast.walk(ast.parse(code[bindings[last['file']]]))if isinstance(n,ast.Call)and n.lineno==last['line']]
    if len([n for n in calls if ast.unparse(n.func)=='page.wait_for_function'])!=1:raise ValueError('Actual native render readiness wait required')
    tree=ast.parse(code['src/lab_generate_skill/gobrowse_runtime.py']);rollout=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run_browser_rollout');calls=[n for n in ast.walk(rollout)if isinstance(n,ast.Call)];reset=[n.lineno for n in calls if ast.unparse(n.func)=='session.reset'];generate=[n.lineno for n in calls if ast.unparse(n.func)=='backend.generate']
    if len(reset)!=1 or len(generate)!=1 or reset[0]>=generate[0]:raise ValueError('Frozen environment reset must precede any actual model request')
    return claim


class SurfacePngContinuation(HardwareFailureContinuation):
    version=VERSION
    lease_name=LEASE
    binding_name=BINDING

    def verify_origin(self):
        s=self.spec
        if s.get('version')!=VERSION or s.get('source_task_ids')!=list(SOURCES) or s.get('sources')!=list(TASKS) or s.get('old_job')!=OLD_JOB or s.get('api_calls')!=0 or s.get('old_model_requests')!=0:raise ValueError('Only the declared single zero-request source may continue')
        if self.terminal_query(OLD_JOB)!={OLD_JOB:'COMPLETED'}:raise ValueError('Original allocation must be completed')
        origin=Path(s['origin']).resolve();base=origin/'progress';wave=base/'png2';bundle=base/'actor-bundles/surfaces5'
        if origin.name!='surfaces-first-actor-v175' or Path(s['wave']).resolve()!=wave or Path(s['old_bundle']).resolve()!=bundle:raise ValueError('Exact original multiwave producer paths required')
        expected={'submitted':origin/'submitted.json','producer':origin/'plan.json','claim':wave/'first-actor-claim/preflight.json','plan':bundle/'plan.json','state':bundle/'worker-state.json','local':bundle/'local-output-state.json','claimed':bundle/'claimed-waves.json','termination':origin/'termination.json','leases':origin/'actor-source-history/source-leases.json','review':origin.parent/'surfaces-actor-independent-review-v175/independent-review.json'}
        if set(s['pins'])!=set(expected)or any(Path(s['pins'][k]['path']).resolve()!=p for k,p in expected.items()):raise ValueError('Complete canonical original metadata pins required')
        rows={k:read_pin(ref)for k,ref in s['pins'].items()};plan=rows['plan'];original=rows['claim'];local=rows['local'];state=rows['state'];review=rows['review']
        if (rows['submitted'].get('job_id')!=OLD_JOB or rows['submitted'].get('plan')!=s['pins']['producer'] or plan.get('base')!=str(base)or plan.get('domain')!='map'or plan.get('tasks')!=5 or plan.get('api_calls')!=0 or len(plan.get('waves',[]))!=2 or plan['waves'][1]!=original or rows['claimed']!=plan['waves']):raise ValueError('Original five-source two-wave first claim differs')
        if (state.get('status')!='completed'or state.get('api_calls')!=0 or state.get('completed_waves')!=[dict(wave=w['wave'],tasks=w['tasks'],result_records=w['tasks'])for w in plan['waves']]or local.get('services_closed')is not True or local.get('bundle')!=str(bundle)or local.get('plan_sha256')!=s['pins']['plan']['sha256']or set(local['waves'])!={w['wave']for w in plan['waves']}or any(x['status']!='runner_closed'for x in local['waves'].values())):raise ValueError('All original source workers and services must be closed')
        termination=rows['termination']
        if termination.get('confirmed')is not True or termination.get('returncode')!=0 or termination.get('group',{}).get('live_members')!=[] or termination.get('scope',{}).get('live_scratch_references')!=[] or termination.get('scope',{}).get('unreadable_same_uid_pids')!=[]:raise ValueError('Original process groups and scratch writers must be quiet')
        if (review.get('passed')is not True or review.get('actor_job')!=OLD_JOB or review.get('plan')!=s['pins']['producer']or review.get('capsule')!=rows['producer']['capsule']or review.get('termination')!=s['pins']['termination']or review.get('source_leases')!=s['pins']['leases']or review.get('full_partition_coverage_verified')is not True or review.get('requests_reconstructed')!=4):raise ValueError('Independent complete original execution review required')
        if self.terminal_query(review['reader_job'])!={review['reader_job']:'COMPLETED'}:raise ValueError('Independent zero-request reader must be completed')
        reviewed=review['sources']+review['unknown_sources'];selected=[r for r in reviewed if r['source_task_id']in SOURCES]
        if len(reviewed)!=5 or len({r['source_task_id']for r in reviewed})!=5 or {r['source_task_id']for r in selected}!=set(SOURCES):raise ValueError('All original five sources must remain represented')
        targets={r['source_task_id']:r for r in selected}
        for target in targets.values():
            if target.get('zero_inference_verified')is not True or target.get('model_requests')!=0 or target.get('status')!='unknown' or target.get('reward')is not None or target.get('diagnosis')!='initial_native_render_timeout_before_model_request':raise ValueError('Only independently verified zero-request PNG initialization timeouts may continue')
        if set(s['wave_indexes'])!={w['wave']for w in plan['waves']} or any(Path(s['wave_indexes'][w['wave']]['path']).resolve()!=Path(w['wave'])/'actor/0/diagnostic-members.json'for w in plan['waves']):raise ValueError('Both original complete wave indexes must remain pinned')
        all_contracts=[];siblings={}
        for w in plan['waves']:
            wp=Path(w['wave'])
            if wp.parent!=base or digest(w['manifest'])!=w['manifest_sha256']or digest(wp/'contracts.jsonl')!=w['contracts_sha256']or digest(base/'inventory.jsonl')!=w['inventory_sha256']:raise ValueError('Original manifest, public contract or inventory drift')
            for proof in w['proofs']:pinned(proof['file'],proof['sha256'])
            contracts=[json.loads(line)for line in regular_bytes(w['manifest']).decode().splitlines()];all_contracts.extend(contracts)
            for c in contracts:
                if c['task_id']not in TASKS:siblings[c['task_id']]=wp/'actor/0'/c['task_id']/'result.json'
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
        if set(s['sibling_results'])!=set(siblings)or any(Path(s['sibling_results'][k]['path']).resolve()!=p for k,p in siblings.items()):raise ValueError('All three unselected sibling results must stay pinned')
        for ref in s['sibling_results'].values():read_pin(ref)
        leases=rows['leases']
        if leases.get('state')!='acquired'or leases.get('closed')is not True or leases.get('claims_released')is not False or leases.get('process',{}).get('job_id')!=OLD_JOB or leases.get('original_inventory',{}).get('sha256')!=original['inventory_sha256']:raise ValueError('Retain all original source-exclusive claims')
        for ref in leases['claims'].values():read_pin(ref)
        if not set(SOURCES)<=leases['claims'].keys():raise ValueError('Selected original source lease missing')
        cap=read_pin(rows['producer']['capsule']);pinned(cap['archive'],cap['archive_sha256']);code={}
        with tarfile.open(cap['archive'])as tar:
            for name in ORIGINAL_CODE:
                member=tar.getmember(name)
                if not member.isfile():raise ValueError('Regular original executed code required')
                raw=tar.extractfile(member).read()
                if dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())!=cap['members'][name]:raise ValueError('Original frozen executable differs')
                code[name]=raw
        if set(s['task_archives'])!=set(SOURCES):raise ValueError('Both complete source archives required')
        self.old_claim_bytes={};self.allowed_old_artifacts={}
        for sid,task in zip(SOURCES,TASKS):
            target=targets[sid];refs=s['task_archives'][sid]
            if refs!=dict(archive=target['archive'],manifest=target['manifest']):raise ValueError('Exact independently reviewed source archive required')
            raw=archive_bytes(refs['archive']['path'],refs['archive']['sha256'],refs['manifest']['path'],refs['manifest']['sha256']);zero_request_png_failure(raw,code,sid)
            self.old_claim_bytes[task]=raw['attempt-started.json'];marker=wave/'actor/0'/task/'attempt-archive.json';m=json.loads(regular_bytes(marker));index_ref=s['wave_indexes'][str(wave)]
            if m.get('archive_path')!=refs['archive']['path']or m.get('archive_sha256')!=refs['archive']['sha256']or m.get('raw_member_count')!=len(raw)or m.get('first_completed_generation_member')is not None or m.get('automatic_retry')is not False or m.get('partition_index_sha256')!=index_ref['sha256']:raise ValueError('Original complete PNG archive marker differs')
            self.allowed_old_artifacts[marker.resolve()]=digest(marker)
            for name in ('result.json','trajectory.json'):
                path=wave/'actor/0'/task/name
                if regular_bytes(path)!=raw[name]:raise ValueError('Retained original PNG artifact differs from raw archive')
                self.allowed_old_artifacts[path.resolve()]=digest(path)
        if s['retained_artifacts']!={str(k):v for k,v in self.allowed_old_artifacts.items()}:raise ValueError('Exact original retained PNG artifacts required')
        manifest=Path(s['subset_manifest']).resolve()
        if manifest.parent!=wave or manifest in (Path(original['manifest']),wave/'contracts.jsonl'):raise ValueError('Separate immutable original-wave subset manifest required')
        claim,contracts=selected_claim(original,[c for c in all_contracts if c['task_id']in {p['task_id']for p in original['proofs']}],manifest,list(TASKS))
        if [c.get('source_task_id')for c in contracts]!=list(SOURCES):raise ValueError('Original source identity changed')
        repair=read_pin(s['repair_review']);cold=read_pin(s['cold_readiness_review'])
        if (not repair.get('passed')or repair.get('changed_sources')!=sorted(SOURCES)or not repair.get('only_two_previously_unregistered_png_sources_changed')or not repair.get('all_existing_functions_ast_unchanged_except_one_capability_predicate')or repair.get('public_target_used')is not False or repair.get('native_cold_readiness_review')!=s['cold_readiness_review']):raise ValueError('Exact minimal public-initial-view repair review required')
        if (cold.get('passed')is not True or cold.get('original_control_cases_replayed')!=60 or cold.get('fresh_factories')!=2 or cold.get('full_archive_members_verified')!=163 or cold.get('model_inference_calls')!=0 or cold.get('actor_calls')!=0 or cold.get('actor_permission')is not False or {r['source_task_id']for r in cold['sources']}!=set(SOURCES)):raise ValueError('Both original-source cold input and native control replays required')
        if self.terminal_query(cold['reader_job'])!={cold['reader_job']:'COMPLETED'}or self.terminal_query(cold['producer_job'])!={cold['producer_job']:'COMPLETED'}:raise ValueError('Cold diagnostic and independent reader must be complete')
        for key in ('plan','archive','manifest'):pinned(cold[key]['path'],cold[key]['sha256'])
        for c in contracts:
            r=next(r for r in cold['sources']if r['source_task_id']==c['source_task_id'])
            if r.get('passed')is not True or r.get('initial_public_start')!=c['start_path']or r.get('full_reset_verified')is not True or r.get('closed_renderer_stream_verified')is not True or r.get('ordinary_input_replay',{}).get('registered_initial_input_verified')is not True:raise ValueError('Exact original public input and native reset proof required')
        if set(s['repair_runtime_pins'])!=REPAIR_FILES or s['repair_runtime_pins']['src/lab_generate_skill/map_tile_warmup.py']['sha256']!=repair['candidate_file']['sha256']:raise ValueError('Exact minimal PNG repair and scoped authority files required')
        for ref in s['repair_runtime_pins'].values():pinned(ref['path'],ref['sha256'])
        preserved=s['preserved_surface78'];publication=read_pin(preserved['publication']);otherreview=read_pin(preserved['independent_review']);post=read_pin(preserved['postcheck'])
        if not publication.get('passed')or publication.get('sources')!=['78e26845a858ef34bdc1']or publication.get('actual_actor_jobs')!=['4607583']or not post.get('passed')or not otherreview.get('passed')or otherreview.get('original_zero_request_verified')is not True or otherreview.get('original_four_sibling_results_preserved')is not True:raise ValueError('Already completed reverse source continuation must remain preserved')
        other_result=read_pin(preserved['result'])
        if other_result.get('evaluation')!=otherreview['sources'][0]['judgment']or other_result.get('error')is not None or other_result.get('task_id')!='78e26845a858ef34bdc1--native-surface-training-v1':raise ValueError('Valid reverse-source outcome cannot be replayed by PNG authority')
        if s['new_shared_out']!=str(wave/'actor'/LEASE):raise ValueError('Dedicated continuation output required')
        if (wave/'first-actor-claim'/LEASE).exists()and self.lease is None:raise ValueError('This continuation is already claimed')
        self.wave,self.bundle,self.claim,self.old_job=wave,bundle,claim,OLD_JOB
        self.contracts,self.sources=contracts,list(TASKS)
        return claim

    def start(self,bundle,local_out,*,runtime_project,manifest_path):
        if 'runtime_review'not in self.spec:raise ValueError('Independent repaired-runtime admission review required before execution')
        review=read_pin(self.spec['runtime_review'])
        origin_spec={k:v for k,v in self.spec.items()if k!='runtime_review'}
        identity=hashlib.sha256(json.dumps(origin_spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if (review.get('version')!='png2-current-runtime-preflight-v1' or review.get('passed')is not True or review.get('source_task_ids')!=list(SOURCES) or review.get('origin_spec_sha256')!=identity or review.get('zero_request_origin_verified')is not True or review.get('old_registered_sources_verified')!=1956 or review.get('ordinary_source_admission_verified')is not True or review.get('model_inference_calls')!=0):raise ValueError('Complete current-runtime/source verification must bind this exact origin and repair')
        if self.terminal_query(review['reader_job'])!={review['reader_job']:'COMPLETED'}:raise ValueError('Repaired-runtime reader is not confirmed complete')
        cap=read_pin(review['capsule'])
        for name,ref in cap['members'].items():
            if Path(name).is_absolute()or '..'in Path(name).parts or digest(Path(runtime_project)/name)!=ref['sha256']:raise ValueError('Actual complete executing capsule differs from independently verified runtime')
        for name,ref in self.spec['repair_runtime_pins'].items():
            if digest(Path(runtime_project)/name)!=ref['sha256']:raise ValueError('Executing continuation code differs from reviewed candidate')
        if Path(__file__).resolve()!=Path(runtime_project).resolve()/'src/lab_generate_skill/surface_png_continuation.py':raise ValueError('Continuation authority imported outside executing project')
        return super().start(bundle,local_out,runtime_project=runtime_project,manifest_path=manifest_path)
