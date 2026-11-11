"""Exact saved website association/attribute tasks in the shared Admin entry."""
from pathlib import Path
from copy import deepcopy
import hashlib,importlib,json
SOURCES={'9aecbe6c890525d67975':'website','a73e169e685b1bcbfb7a':'attribute'}
VERSION='source-bound-native-material-save-v186'
PROTOCOL='native_material_save'

def read(ref):
    if not isinstance(ref,dict)or set(ref)!={'path','sha256'}:raise ValueError('Exact evidence pin required')
    p=Path(ref['path'])
    if not p.is_absolute()or p.is_symlink()or not p.is_file():raise ValueError('Pinned absolute regular evidence required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Reviewed evidence changed: '+str(p))
    return json.loads(raw)

def is_material_save_source(row):
    return row.get('source_task_id')in SOURCES or row.get('task_protocol')==PROTOCOL or 'material_save_admission'in row

def material_save_fixture_source(source,ordinary_fixture):
    return 'f06b77b2331bb8209410'if source in SOURCES else ordinary_fixture(source)

def registry(project):
    project=Path(project).resolve();runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    ref=runtime.get('reviewed_admin_material_save');config=read(ref)
    if config.get('version')!=VERSION or set(config.get('sources',{}))!=set(SOURCES):raise ValueError('Exact two material source identities required')
    compat=read(config['compatibility_review'])
    if not compat.get('passed')or compat.get('candidate_files')!=config.get('candidate_files')or compat.get('first_actor_reviews')!=config.get('first_actor_reviews'):raise ValueError('Current source compatibility proof required')
    expected={'src/lab_generate_skill/admin_material_save_current.py','scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'}
    if set(compat.get('dispatch_files',{}))!=expected:raise ValueError('Complete ordinary dispatch binding required')
    files={**config['candidate_files'],**compat['dispatch_files'],**compat['unchanged_execution_dependencies']}
    for name,digest in files.items():
        p=project/name
        if Path(name).is_absolute()or '..'in Path(name).parts or p.is_symlink()or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Current material execution bytes changed: '+name)
        if runtime['actor_submission']['files_sha256'].get(name)!=digest:raise ValueError('Unfrozen current material execution file')
    native=read(config['native_control_review']);shared=read(config['shared_entry_review'])
    if not(shared.get('passed')and shared.get('registered')==1965 and shared.get('all_runtime_files_verified')):raise ValueError('Complete pre-existing published interface proof required')
    if not(native.get('passed')and native.get('shared_reset_verified')and native.get('website_controls_qualified')and native.get('attribute_controls_qualified')and native.get('qualified_native_controls')==8):raise ValueError('All eight actual native controls and full resets required')
    contracts=json.loads((project/'scripts/admin_material_save/public-contracts.json').read_text())
    if set(contracts)!=set(SOURCES.values())or contracts!=read(config['public_contracts']):raise ValueError('Exact published material contracts required')
    for sid,kind in SOURCES.items():
        c=contracts[kind];entry=config['sources'][sid];actor=read(config['first_actor_reviews'][kind]);case=actor.get('cases',{}).get(kind,{})
        if not(actor.get('passed')and actor.get('actual_first_actor_reviewed')and actor.get('full_reset_verified')and actor.get('job_id')==entry['first_actor_job']):raise ValueError('Closed first-Actor and full reset review required')
        if not(case.get('passed')and case.get('source_task_id')==sid and case.get('status')in('success','failure')and case.get('actual_first_actor_reviewed')and case.get('requests',{}).get('stopping_policy_replayed')):raise ValueError('Actual source-bound public requests and normal stopping required')
        typed=read(entry['typed_input_review'])
        if not typed.get('passed'):raise ValueError('Current actual input replay required')
        if c['source_task_id']!=sid or c['answer_fields']!={}or c['init_task_id']!='f06b77b2331bb8209410':raise ValueError('Published source task differs')
        row=entry['source_task_row']
        if row['goal']!=c['goal']or row['runtime_task_id']!=c['task_id']or row['source_goal']!=c['original_goal']:raise ValueError('Public task row differs')
    return ref,config,contracts

def prepare_material_save_row(task,*,project):
    ref,config,contracts=registry(project);sid=task.get('source_task_id')
    if sid not in SOURCES or task.get('task_protocol')!=PROTOCOL or task.get('material_save_admission')!=ref or task.get('source_row')!=config['sources'][sid]['source_task_row']:raise ValueError('Registered material entry differs from current source authority')
    return dict(deepcopy(config['sources'][sid]['source_task_row']),task_protocol=PROTOCOL,material_save_admission=ref)

def material_save_admission(row,project):
    ref,config,contracts=registry(project);sid=row.get('source_task_id')
    if sid not in SOURCES or row!=dict(config['sources'][sid]['source_task_row'],task_protocol=PROTOCOL,material_save_admission=ref):raise ValueError('Source-bound material admission differs')
    c=contracts[SOURCES[sid]]
    binding=dict(source_task_id=sid,runtime_task_id=c['task_id'],goal=c['goal'],start_path=c['start_path'],answer_fields={},spec=dict(kind=PROTOCOL,initial_ui_steps=c['initial_ui_steps']),task_revision=c['task_revision'])
    return dict(passed=True,binding=binding,original_controls_replayed=False,retained_native_controls_verified=True,training_admitted=False)

def run_material_save(row,project,site,directory,settings,backend):
    from lab_generate_skill.io_utils import atomic_write_json as save
    from lab_generate_skill.admin_pilot import render_task
    from lab_generate_skill.runtime_watchdog import deadline_scope
    directory=Path(directory);sid=row['source_task_id'];kind=SOURCES[sid]
    if not(directory/'attempt-started.json').is_file():raise ValueError('Ordinary batch attempt claim required')
    material_save_admission(row,project);_,_,contracts=registry(project);c=contracts[kind]
    module=importlib.import_module('admin_material_save.ordinary_actor');state_module=importlib.import_module('admin_material_save.support.full_state')
    package=Path(project).resolve()/'scripts/admin_material_save'
    if Path(module.__file__).resolve()!=package/'ordinary_actor.py'or Path(state_module.__file__).resolve()!=package/'support/full_state.py':raise ValueError('Material modules belong to another runtime')
    manager=state_module.FullState(site,directory/'full-state',package/'support')
    with deadline_scope('material_original_baseline',600,result_path=directory/'baseline-timeout.json'):manager.prepare()
    try:result=module.run_one(site,directory/'native-material',kind,c,settings,backend,manager)
    finally:
        if not manager.safe_to_restore:raise RuntimeError('Browser closure unavailable; unsafe material reset')
        with deadline_scope('material_full_original_reset',600,result_path=directory/'reset-timeout.json'):reset=manager.restore('final',release=True)
        if not reset['passed']:raise RuntimeError('Material original state reset failed')
    registry(project);trace=json.loads((directory/'native-material/trajectory.json').read_text())
    invalid=sum(not m.get('action_payload')for m in trace['messages']if m['role']=='assistant')
    result.update(task_id=sid,goal=c['goal'],invalid_generations=invalid,full_original_reset=reset,
        codebase_status='requires_diagnosis'if trace.get('error')or result['evaluation']['status']=='unknown'or invalid else'interface_exercised',trajectory='native-material/trajectory.json')
    save(directory/'result.json',result);render_task(directory,result)
    if trace.get('error')or result['evaluation']['status']=='unknown':raise RuntimeError('Material runtime/evidence failure remains unscored')
    return result
