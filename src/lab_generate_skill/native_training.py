"""Explicit formal-native contract and offline SFT import, never pilot promotion.

The caller supplies the trusted native reviewer, full source closure reviewer,
and Teacher input processor. No evaluator or callback is imported from records.
This additive candidate does not provide a site/model launcher or API release.
"""
from copy import deepcopy
from dataclasses import asdict
import csv
import inspect
import json
import math
from pathlib import Path

from .config import GenerationSettings
from .data_scope import filter_bank, require_runtime_references
from .evaluator_feedback import teacher_evidence
from .generator_sft import file_hash, fingerprint, generator_messages, normalize_goal, split_groups, write_jsonl
from .io_utils import atomic_write_json
from .local_stage1_driver import Policy, TEACHER_SYSTEM, best_successful, parse_skill, run_task
from .stage1_local import LocalRolloutValidator, read_pinned_json
from .sft_train import encode_supervised_record, require_training_sft_record


def require(value, message):
    if not value:
        raise ValueError(message)


def pin(path):
    return dict(path=str(Path(path).resolve()), sha256=file_hash(path))


def formal_teacher_settings():
    """Exact existing run_webarena_stage1.py Teacher settings, no backend construction."""
    return GenerationSettings(backend='openai',model='openai/gpt-5.6-terra',
        api_base='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',reasoning_effort='medium',
        max_new_tokens=4096,structured_skill=True,send_sampling_parameters=False).model_dump(mode='json')


def native_generator_settings(root):
    return GenerationSettings(backend='transformers',model=str(Path(root)/'models/Qwen3-8B'),
        temperature=.7,max_new_tokens=1024,max_input_tokens=16384,
        enable_thinking=False,dtype='bfloat16').model_dump(mode='json')


def callback_pin(callback, expected):
    path=inspect.getsourcefile(callback)
    # The published source must remain pinned. A verified frozen capsule may
    # relocate identical source bytes; its dependencies are attested separately.
    require(path is not None and pin(expected['path'])==expected
        and file_hash(path)==expected['sha256'], 'Trusted callback implementation differs')


def registered_goal(plan, contract):
    """Keep literal registration distinct from the native public query schema."""
    if plan.get('native_source_adapter') in ('registered_admin_declarative_v1', 'registered_admin_legacy_v1'):
        from admin_declarative_binding import resolve
        from admin_declarative_runtime import CATALOG_VERSIONS
        source = plan['sources'][0]
        binding = resolve(plan['source_binding_catalog'], source['source_task_id'])['source']
        catalog = read_pinned_json(plan['source_binding_catalog'])
        require(catalog['training_pointer'] == plan['training_pointer'] and source['profile'] == plan['native_source_adapter']
                and catalog['version'] == CATALOG_VERSIONS[plan['native_source_adapter']]
                and all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id',
                    'runtime_task_id', 'domain', 'native_contract', 'admission', 'source_row', 'evaluator_version')),
                'Declarative source differs from registered input')
        require(contract['public_goal'] == binding['actor_goal'], 'Declarative public interface changed')
        return binding['public_goal']
    if plan.get('native_source_adapter') not in ('registered_reddit_retained_reading_v1', 'registered_query_v1', 'registered_gitlab_browser_artifact_v1', 'registered_map_typed_v1', 'registered_grouped_v1', 'registered_map_export_v1', 'registered_shopping_read_v1', 'registered_gitlab_native_goal_v1', 'registered_map_route_family_v1', 'registered_map_account_v1', 'registered_map_content_v1', 'registered_map_node_v1', 'registered_map_raster_v1', 'registered_map_link_v1', 'registered_map_overlay_v1', 'registered_map_surface_v1', 'registered_gitlab_artifact_v1', 'registered_gitlab_document_v1', 'registered_map_provider_v1', 'registered_map_finite_v1', 'registered_map_facts_v1', 'registered_route_v1', 'registered_reading_v1', 'registered_gitlab_read_v1', 'registered_reddit_native_v1', 'registered_shopping_offline_v1'):
        return contract['public_goal']
    if plan.get('native_source_adapter') == 'registered_reddit_native_v1':
        from reddit_native_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_shopping_offline_v1':
        from shopping_offline_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_gitlab_read_v1':
        from gitlab_read_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_reddit_retained_reading_v1':
        from reddit_retained_reading_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_reading_v1':
        from reading_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_export_v1':
        from map_export_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_gitlab_native_goal_v1':
        from gitlab_native_goal_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_shopping_read_v1':
        from shopping_read_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_facts_v1':
        from map_facts_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_route_family_v1':
        from map_route_family_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_account_v1':
        from map_account_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_content_v1':
        from map_content_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_node_v1':
        from map_node_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_raster_v1':
        from map_raster_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_link_v1':
        from map_link_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_overlay_v1':
        from map_overlay_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_gitlab_browser_artifact_v1':
        from gitlab_browser_artifact_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_typed_v1':
        from map_typed_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_surface_v1':
        from map_surface_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_gitlab_artifact_v1':
        from gitlab_artifact_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_gitlab_document_v1':
        from gitlab_document_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_provider_v1':
        from map_provider_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_map_finite_v1':
        from map_finite_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_route_v1':
        from route_sft_binding import VERSION, validate_binding
    elif plan.get('native_source_adapter') == 'registered_grouped_v1':
        from grouped_sft_binding import VERSION, validate_binding
    else:
        from query_sft_binding import VERSION, validate_binding
    catalog = read_pinned_json(plan['source_binding_catalog'])
    require(catalog['version'] == VERSION and catalog['training_pointer'] == plan['training_pointer'],
            'Query registration catalog differs')
    source = plan['sources'][0]
    binding = catalog['sources'][source['source_task_id']]
    require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
            'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
            'Query source differs from literal registration binding')
    native, admission = (read_pinned_json(source[k]) for k in ('native_contract', 'admission'))
    validate_binding(binding, native, admission)
    require(contract['public_goal'] == binding['actor_goal'], 'Public query interface changed')
    return binding['public_goal']


class NativeTrainingValidator(LocalRolloutValidator):
    """Reuse the exact native rollout checks with a separately released contract.

    Only construction differs from LocalRolloutValidator. Its context and native
    __call__ methods remain inherited, including actual skill/request and receipt
    checks. A changed label on an old pilot cannot change its original receipt SHA.
    """
    def __init__(self, contract_ref, *, source_plan_ref, authorization_ref, review_execution):
        self.contract_ref=deepcopy(contract_ref)
        self.contract=read_pinned_json(contract_ref)
        self.contract_sha256=contract_ref['sha256']
        self.review_execution=review_execution
        self.source_plan_ref=deepcopy(source_plan_ref)
        self.authorization_ref=deepcopy(authorization_ref)
        self.plan=read_pinned_json(source_plan_ref)
        self.authorization=read_pinned_json(authorization_ref)
        c,p,a=self.contract,self.plan,self.authorization
        if p.get('actor_memory_policy') is not None:
            from .actor_event_memory import memory_for_policy
            memory_for_policy(p['actor_memory_policy'])
        required={'version','task_id','source_task_id','runtime_task_id','domain','public_goal',
            'website_snapshot_id','runtime_capsule_sha256','evaluator_version','output_purpose','teacher_mode'}
        require(set(c)==required and c['version']=='local-stage1-contract-v1'
            and all(isinstance(v,str) and v.strip() for v in c.values()), 'Formal native contract incomplete')
        require((c['output_purpose'],c['teacher_mode'])==('training','authorized_api'),
            'Pilot or local-replacement contracts cannot enter formal native training')
        require(p['purpose']=='training' and p['training_data'] is True and p['automatic_retry'] is False
            and p['local_contract']==contract_ref and p['policy']==asdict(Policy()), 'Formal source plan changed')
        require(len(p['sources'])==1, 'An explicit single-source formal plan is required')
        self.source=p['sources'][0]
        source=self.source
        require(all(source[k]==c[v] for k,v in [('source_task_id','source_task_id'),
            ('active_task_id','task_id'),('runtime_task_id','runtime_task_id'),('domain','domain'),
            ('evaluator_version','evaluator_version')]) and p['capsule']['sha256']==c['runtime_capsule_sha256'],
            'Formal source/runtime/native identity differs')
        require(p['teacher_settings']==formal_teacher_settings(), 'Existing formal Teacher configuration changed')
        require(p['generator_settings']==native_generator_settings(p['root']), 'Original native Generator configuration changed')
        pointer=read_pinned_json(p['training_pointer']);table=Path(pointer['tasks'])
        require(file_hash(table)==pointer['tasks_sha256'], 'Frozen training registration changed')
        with table.open(newline='', encoding='utf-8-sig') as stream:
            rows=[r for r in csv.DictReader(stream) if r['source_task_id']==c['source_task_id']]
        require(len(rows)==1 and rows[0]['split']=='train' and rows[0]['status'] in ('success','failure')
            and all(rows[0][key]==source[key] for key in ('active_task_id','runtime_task_id','domain'))
            and rows[0]['current_goal']==registered_goal(p,c), 'Source is not the exact registered training task')
        require(a['version']=='native-stage1-training-authorization-v1' and a['source_plan']==source_plan_ref
            and a['user_api_authorized'] is True and a['local_pilot_reported'] is True
            and a['source_task_ids']==[c['source_task_id']]
            and a['teacher_settings_sha256']==fingerprint(p['teacher_settings']), 'Explicit formal release missing')
        limit=a['teacher_cost_stop_usd']
        require(type(limit) in (int,float) and math.isfinite(limit) and limit>0, 'Authorized cost stop missing')
        require(read_pinned_json(a['local_pilot_review']).get('passed') is True, 'Prior passed local pilot proof missing')
        require(callable(review_execution) and getattr(review_execution,'native_ref',None)==source['native_contract']
            and getattr(review_execution,'admission_ref',None)==source['admission']
            and getattr(review_execution,'capsule_ref',None)==p['capsule'], 'Explicit source-bound native reviewer required')

    def validate_context(self, task, start=None, purpose=None):
        require(read_pinned_json(self.source_plan_ref)==self.plan
            and read_pinned_json(self.authorization_ref)==self.authorization, 'Formal source release changed')
        return super().validate_context(task,start,purpose)


from .stage1_execution_steps import METRIC,selection_steps,require_metric


def validate_method_result(result, context, validator):
    """Complete method and all native outcomes; retain valid failures as evidence."""
    require(isinstance(validator,NativeTrainingValidator), 'Explicit formal native capability required')
    c=validator.contract;task=dict(task_id=c['task_id'],domain=c['domain']);start=context['start']
    validator.validate_context(task,start,'training')
    require(context.get('local_reward_contract_sha256')==validator.contract_sha256
        and result.get('local_reward_contract_sha256')==validator.contract_sha256, 'Original formal contract changed')
    require(result['task_id']==c['task_id'] and result['policy']==asdict(Policy()), 'Original four-candidate policy changed')
    require_metric(result);require_metric(context)
    attempts=result['attempts']
    require(5<=len(attempts)<=7, 'Four candidates and mandatory Teacher validation required')
    reviewed=[]
    for i,attempt in enumerate(attempts):
        kind,index=('bootstrap',i) if i<4 else ('teacher',i-3)
        require(attempt['source']==kind and attempt['index']==index, 'Non-contiguous candidate/Teacher history')
        if i>4:
            require(best_successful(reviewed) is None, 'Teacher continued after required successful round')
        ref=dict(path=attempt['validation']['trajectory_path'],sha256=attempt['validation']['trajectory_sha256'])
        trace=read_pinned_json(ref)
        success=validator(trace,task,start,attempt['skill'])
        require_metric(attempt)
        require(type(attempt['success']) is bool and success==attempt['success']
            and type(attempt['steps']) is int and type(attempt['generation_rounds']) is int
            and selection_steps(trace)==attempt['steps']
            and trace['rounds']==attempt['generation_rounds'],
            'Native candidate outcome or step count changed')
        reviewed.append(dict(attempt,trajectory=trace))
    best=best_successful(reviewed)
    require(best is not None or len(attempts)==7, 'Failed source omitted remaining Teacher rounds')
    require(result['status']==('accepted' if best else 'rejected'), 'Native result/selection changed')
    if best is None:
        require('verified_record' not in result, 'No success must produce no positive target')
        return reviewed,None
    record=result['verified_record'];meta=record['metadata'];require_metric(meta)
    require(record['task_id']==c['task_id'] and record['task_type']==c['domain']
        and record['target']==best['skill'] and meta['validation']==best['validation'], 'Selected target is not stable best success')
    require(record['input']==dict(task=start['task'],initial_observation=start['initial_observation'],
        generator_observation=start['generator_observation'],retrieved_skills=context['refs']), 'Saved generator input changed')
    require(meta['training_data'] is True and meta['output_purpose']=='training'
        and meta.get('teacher_mode')=='authorized_api' and meta['local_reward_contract_sha256']==validator.contract_sha256
        and meta['website_snapshot_id']==c['website_snapshot_id'] and meta['actor_success'] is True
        and meta['verification_steps']==best['steps']
        and meta['verification_generation_rounds']==best['generation_rounds'] and meta['source']==best['source']
        and meta['accepted_round']==(best['index'] if best['source']=='teacher' else 0)
        and meta['candidate_index']==(best['index'] if best['source']=='bootstrap' else None), 'Formal target metadata differs')
    require(meta.get('models',{}).get('teacher')==validator.plan['teacher_settings']['model']
        and meta.get('models',{}).get('teacher_mode')!='local_replacement', 'Formal Teacher metadata differs')
    return reviewed,record


def run_native_training_task(task,directory,*,validator,**callbacks):
    """Method adapter only; it does not grant model/API/claim launch permission.

    Fresh/partial work uses the unchanged policy; complete results use the formal
    resume validator instead of the old pilot-only resume gate. Export still
    needs independent closed-source and exact request replay below.
    """
    require(isinstance(validator,NativeTrainingValidator), 'Formal native capability required')
    validator.validate_context(task,purpose='training')
    require(not {'purpose','local_validator','policy'} & callbacks.keys(), 'Method policy cannot be overridden')
    directory=Path(directory);final=directory/'result.json'
    if final.exists():
        result=json.loads(final.read_text());context=json.loads((directory/'context.json').read_text())
        validate_method_result(result,context,validator)
        return result
    return run_task(task,directory,purpose='training',local_validator=validator,**callbacks)


def validate_model_requests(base,context,reviewed,validator,teacher_messages):
    """Reconstruct exact requests through original parse/dedup/Teacher evidence."""
    base=Path(base);p=validator.plan;sid=validator.contract['source_task_id']
    callback_pin(teacher_messages,p['teacher_input_processor'])
    from .teacher_evidence_projection import VERSION, project
    mode=p.get('teacher_input_format','identity_full_teacher_messages_v1')
    require(mode in ('identity_full_teacher_messages_v1',VERSION), 'Unknown Teacher input format')
    projected=mode==VERSION
    if projected:
        callback_pin(project,p['teacher_projection_implementation'])
    paths=sorted((base/'requests').iterdir())
    require(all(path.is_file() and not path.is_symlink() and path.suffix=='.json' for path in paths), 'Unexpected request ledger entry')
    ledger_pins=[pin(path) for path in paths]
    ledger={Path(ref['path']).name:read_pinned_json(ref) for ref in ledger_pins};used=set();teacher_refs=[]
    def response(key,messages,seed,settings,paid,raw=None):
        name=fingerprint([sid,key])+'.json';value=ledger.get(name,{})
        require(value.get('key')==[sid,key] and value.get('status')=='complete' and value.get('paid') is paid,
            'Missing, foreign or unresolved actual model request')
        expected_request=dict(messages=messages,model=settings['model'],seed=seed,settings=settings)
        require(value.get('contract')==fingerprint(dict(key=[sid,key],**expected_request)),
            'Actual request/model/settings differ')
        require(value.get('request')==expected_request,
            'Complete saved model request is missing or differs from reconstructed input')
        answer=value['response']
        if paid:
            cost=answer.get('cost')
            require(type(cost) in (int,float) and math.isfinite(cost) and cost>=0
                and isinstance(answer.get('provider_response_id'),str) and bool(answer['provider_response_id'])
                and answer.get('api_error_type') is None and answer.get('api_error_code') is None,
                'Formal Teacher actual response/cost not proved')
            before=sum(r['cost'] for r in teacher_refs);budget=value.get('budget_check',{})
            require(budget.get('budget_usd')==validator.authorization['teacher_cost_stop_usd']
                and budget.get('reported_cost_usd')==before and before<budget['budget_usd']
                and budget.get('estimate',{}).get('context_fits') is True,
                'Actual paid request lacks original authorized budget precheck')
            actual_ref=pin(base/(key+'-actual-input.json'));actual=read_pinned_json(actual_ref)
            teacher_ref=dict(request=pin(base/'requests'/name),actual_input=actual_ref,cost=cost)
            if projected:
                from .native_api_callbacks import projected_teacher_input
                expected_messages,projection_audit=projected_teacher_input(raw,key)
                require(messages==expected_messages, 'Teacher send/review processor differs')
                raw_ref=pin(base/(key+'-raw-input.json'));original=read_pinned_json(raw_ref)
                require(original==dict(messages=raw,seed=seed,source_plan=validator.source_plan_ref),
                    'Original complete Teacher input differs')
                require(actual==dict(messages=messages,seed=seed,input_processing=VERSION,raw_input=raw_ref,
                    projection_audit=projection_audit,raw_messages_sha256=fingerprint(raw),source_plan=validator.source_plan_ref),
                    'Actual dispatched Teacher input or projection provenance differs')
                teacher_ref['raw_input']=raw_ref
            else:
                require(actual['messages']==messages and actual['seed']==seed, 'Actual dispatched Teacher input differs')
            teacher_refs.append(teacher_ref)
        used.add(name)
        return answer
    start,refs=context['start'],context['refs'];messages=generator_messages(start['task'],start['generator_observation'],refs)
    seen=set()
    for i in range(4):
        for retry in range(5):
            settings=dict(p['generator_settings'],temperature=min(1.2,.7+.1*retry))
            skill=parse_skill(response(f'bootstrap-{i}-{retry}',messages,42+i+retry*4,settings,False))
            key=fingerprint(skill)
            if key not in seen or retry==4:break
        seen.add(key);require(skill==reviewed[i]['skill'], 'Actual Generator candidate differs')
    for i in range(4,len(reviewed)):
        previous=reviewed[:i];evidence=teacher_evidence(start,refs,previous,best_successful(previous))
        raw=[dict(role='system',content=TEACHER_SYSTEM),dict(role='user',content=json.dumps(evidence,ensure_ascii=False))]
        key='teacher-'+str(i-3);selected=teacher_messages(raw,key)
        skill=parse_skill(response(key,selected,42+i-4,p['teacher_settings'],True,raw=raw))
        require(skill==reviewed[i]['skill'], 'Actual revised skill differs from validated candidate')
    require(used==set(ledger), 'Unresolved or unconsumed request ledger tail')
    require(sorted((base/'requests').iterdir())==paths, 'Original request ledger inventory changed')
    for ref in ledger_pins:require(pin(ref['path'])==ref, 'Original request ledger changed')
    return dict(actual_model_requests_verified=len(used),teacher_requests=teacher_refs,
                teacher_reported_cost_usd=sum(r['cost'] for r in teacher_refs),request_files=ledger_pins)


def audit_native_training_source(base,*,validator,teacher_messages,review_closed_source,execution_job_id):
    """Offline import needs both native replay and a trusted whole-source closure review."""
    require(isinstance(validator,NativeTrainingValidator), 'Formal native capability required')
    base=Path(base).resolve();p=validator.plan
    require(str(base)==p['result_directory'], 'Original formal source directory differs')
    callback_pin(review_closed_source,p['complete_source_reviewer'])
    closure=review_closed_source(base,validator.source_plan_ref)
    require(isinstance(closure,dict) and closure.get('passed') is True
        and closure.get('source_plan')==validator.source_plan_ref
        and closure.get('source_task_id')==validator.contract['source_task_id']
        and closure.get('capsule')==p['capsule'] and closure.get('execution_job_id')==execution_job_id
        and isinstance(execution_job_id,str) and execution_job_id.isdecimal()
        and closure.get('closure_verified') is True and closure.get('claim_verified') is True
        and closure.get('initial_qualification_verified') is True
        and closure.get('whole_archive_verified') is True
        and closure.get('full_actual_requests_verified') is True
        and closure.get('unresolved_model_requests')==0 and closure.get('unresolved_actor_episodes')==0
        and bool(closure.get('files')), 'Independent complete source/claim/request/closure proof missing')
    refs=[pin(base/'stage1/context.json'),pin(base/'stage1/result.json'),*closure['files']]
    for ref in refs:require(pin(ref['path'])==ref, 'Original formal evidence changed')
    context,result=map(read_pinned_json,refs[:2])
    reviewed,record=validate_method_result(result,context,validator)
    requests=validate_model_requests(base,context,reviewed,validator,teacher_messages)
    refs.extend(requests['request_files'])
    refs.extend(x['actual_input'] for x in requests['teacher_requests'])
    refs.extend(x['raw_input'] for x in requests['teacher_requests'] if 'raw_input' in x)
    for attempt in reviewed:refs.append(dict(path=attempt['validation']['trajectory_path'],sha256=attempt['validation']['trajectory_sha256']))
    require(review_closed_source(base,validator.source_plan_ref)==closure, 'Independent closed-source proof changed')
    for ref in refs:require(pin(ref['path'])==ref, 'Formal evidence changed during import')
    return dict(version='native-stage1-training-audit-v1',passed=True,source_plan=validator.source_plan_ref,
        authorization=validator.authorization_ref,source_task_id=validator.contract['source_task_id'],
        contract=validator.contract_ref,source_complete=True,closure=closure,files=refs,
        success_flags=[a['success'] for a in reviewed],selected_record=record,
        new_model_calls=0,new_actor_calls=0,new_paid_api_calls=0,**requests)


def export_native_training(sources,*,allowed,reserved_goals,bank,tokenizer,output_dir,max_seq_length=16384,dev_ratio=.05,seed=42):
    """Audit a batch and retain qualified targets until the original split is viable.

    Sources are trusted caller bindings, never callback names loaded from data.
    A candidate file is an accumulation artifact, not a train/dev release. Later
    batches can re-audit the complete source bindings into a new output directory;
    this does not dispatch models or accept candidate files as source evidence.
    """
    output_dir=Path(output_dir);require(not output_dir.exists(), 'Use a new export directory')
    audits=[];rows=[];seen=set()
    for binding in sources:
        validator=binding['validator'];c=validator.contract;sid=c['source_task_id']
        require(read_pinned_json(validator.plan['allowed'])==allowed, 'Frozen allowed training goals differ')
        bank_ref=validator.plan['bank'];require(pin(bank_ref['path'])==bank_ref, 'Frozen training bank changed')
        require([json.loads(line) for line in Path(bank_ref['path']).read_text().splitlines() if line.strip()]==bank,
                'Runtime bank differs from formal source plan')
        require(c['task_id'] not in seen, 'Duplicate source target');seen.add(c['task_id'])
        scope=read_pinned_json(validator.plan['scope'])
        reserved=set(reserved_goals)|{tuple(v) for v in scope['reserved_goal_keys']}
        expected=allowed.get(c['task_id'])
        literal_goal=registered_goal(validator.plan,c)
        require(expected is not None and expected['domain']==c['domain']
            and expected['task_instruction']==literal_goal
            and (c['domain'],normalize_goal(literal_goal)) not in reserved
            and (c['domain'],normalize_goal(c['public_goal'])) not in reserved,
            'Formal target outside literal training scope')
        audit=audit_native_training_source(**binding);audits.append(audit)
        record=audit['selected_record']
        if record is None:continue
        blocked={sid,c['task_id'],c['runtime_task_id']}|set(scope['blocked_bank_source_task_ids'])
        reserved|={(c['domain'],normalize_goal(literal_goal))}
        eligible,_=filter_bank(bank,blocked,reserved,excluded_skill_ids=scope.get('excluded_skill_ids',[]))
        eligible=[r for r in eligible if r['domain']==c['domain']]
        refs=record['input']['retrieved_skills'];ids=[r.get('skill_id') for r in refs]
        require(len(ids)==6 and len(set(ids))==6 and all(ids), 'Six distinct provenance-bound references required')
        require_runtime_references(refs,bank=eligible)
        observation=record['input']['generator_observation']
        require(isinstance(observation,str) and bool(observation.strip()), 'Exact generator observation missing')
        messages=generator_messages(c['public_goal'],observation,refs)
        messages.append(dict(role='assistant',content=json.dumps(record['target'],ensure_ascii=False)))
        item=dict(id=c['task_id'],task_id=c['task_id'],task_type=c['domain'],
            domain=c['domain'],task=c['public_goal'],
            goal_group_id=fingerprint(normalize_goal(literal_goal))[:16],messages=messages,
            metadata=dict(record['metadata'],target_status='environment_verified',native_training_source=validator.source_plan_ref))
        if validator.plan.get('native_source_adapter') in ('registered_query_v1', 'registered_gitlab_browser_artifact_v1', 'registered_map_typed_v1', 'registered_admin_declarative_v1', 'registered_admin_legacy_v1', 'registered_grouped_v1', 'registered_map_export_v1', 'registered_shopping_read_v1', 'registered_gitlab_native_goal_v1', 'registered_map_route_family_v1', 'registered_map_account_v1', 'registered_map_content_v1', 'registered_map_node_v1', 'registered_map_raster_v1', 'registered_map_link_v1', 'registered_map_overlay_v1', 'registered_map_surface_v1', 'registered_gitlab_artifact_v1', 'registered_gitlab_document_v1', 'registered_map_provider_v1', 'registered_map_finite_v1', 'registered_map_facts_v1', 'registered_route_v1', 'registered_reading_v1', 'registered_gitlab_read_v1', 'registered_reddit_native_v1', 'registered_shopping_offline_v1'):
            item['metadata']['registered_goal'] = literal_goal
        require_training_sft_record(item);encode_supervised_record(tokenizer,item,max_seq_length=max_seq_length)
        rows.append(item)
    split_reason=None
    try:
        train,dev=split_groups(rows,dev_ratio,seed)
    except ValueError as error:
        # Preserve the original grouping/stratification algorithm and all other
        # errors. Even two targets can share one goal or separate singleton strata.
        if str(error)!='Not enough goal groups to create train and dev':raise
        train,dev=[],[];split_reason=str(error)
    output_dir.mkdir(parents=True)
    project=lambda items:[{k:v for k,v in item.items() if k not in ('domain','task')} for item in items]
    write_jsonl(output_dir/'candidates.jsonl',project(rows))
    split_files={}
    if split_reason is None:
        for name,items in [('train',train),('dev',dev)]:
            write_jsonl(output_dir/(name+'.jsonl'),project(items))
            split_files[name]=pin(output_dir/(name+'.jsonl'))
    atomic_write_json(output_dir/'native-audits.json',audits)
    summary=dict(complete=True,mode='native-environment-verified',training_data=True,output_purpose='training',
        status=('train_dev_export_ready' if split_reason is None else
                'awaiting_goal_groups' if rows else 'no_positive_targets'),
        train_dev_split_ready=split_reason is None,split_unavailable_reason=split_reason,
        positive_target_accumulation=True,goal_groups=len({normalize_goal(r['task']) for r in rows}),
        formal_training_targets=len(rows),rejected_sources=sum(a['selected_record'] is None for a in audits),
        train=len(train),dev=len(dev),files=split_files,candidates=pin(output_dir/'candidates.jsonl'),
        split_parameters=dict(dev_ratio=dev_ratio,seed=seed),max_seq_length=max_seq_length,
        audit=pin(output_dir/'native-audits.json'),new_model_calls=0,new_actor_calls=0,new_paid_api_calls=0)
    atomic_write_json(output_dir/'summary.json',summary)
    return summary
