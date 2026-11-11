"""Reviewed sales query in the ordinary shared-model Admin entry."""
from pathlib import Path
from copy import deepcopy
import hashlib,importlib,json,sys
SOURCE='19f082255560da530586'
VERSION='source-bound-native-sales-query-v185'
PROTOCOL='native_sales_query'

def read(ref):
    if not isinstance(ref,dict)or set(ref)!={'path','sha256'}:raise ValueError('Exact evidence pin required')
    path=Path(ref['path'])
    if not path.is_absolute()or path.is_symlink()or not path.is_file():raise ValueError('Absolute regular evidence required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Reviewed evidence changed: '+str(path))
    return json.loads(raw)

def is_sales_query_source(row):
    return row.get('source_task_id')==SOURCE or row.get('task_protocol')==PROTOCOL or 'sales_query_admission'in row

def sales_query_fixture_source(source,ordinary_fixture):
    return 'f06b77b2331bb8209410' if source==SOURCE else ordinary_fixture(source)

def registry(project):
    project=Path(project).resolve();runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    ref=runtime.get('reviewed_admin_sales_query');config=read(ref)
    if config.get('version')!=VERSION or config.get('source_task_id')!=SOURCE:raise ValueError('Exact sales source required')
    compat=read(config['compatibility_review'])
    if not compat.get('passed')or compat.get('candidate_files')!=config.get('candidate_files')or compat.get('first_actor_review')!=config.get('first_actor_review'):
        raise ValueError('Current runtime compatibility proof required')
    expected={'src/lab_generate_skill/admin_sales_query_current.py','scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'}
    if set(compat.get('dispatch_files',{}))!=expected:raise ValueError('Complete ordinary dispatch required')
    files={**config['candidate_files'],**compat['dispatch_files'],**compat['unchanged_execution_dependencies']}
    for name,digest in files.items():
        path=project/name
        if Path(name).is_absolute()or '..'in Path(name).parts or path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Current sales execution bytes changed: '+name)
        if runtime['actor_submission']['files_sha256'].get(name)!=digest:raise ValueError('Unfrozen current execution file')
    actor=read(config['first_actor_review']);native=read(config['native_input_review']);typed=read(config['typed_input_review'])
    shared=read(config['shared_entry_review'])
    if not shared.get('passed')or shared.get('source_count')!=1964:
        raise ValueError('Complete pre-existing shared-interface compatibility required')
    if not(actor.get('passed')and actor.get('source_task_id')==SOURCE and actor.get('status')in('success','failure')and actor.get('job_id')==config['first_actor_job']and actor.get('actual_first_actor_reviewed')and actor.get('full_reset_verified')and actor.get('query_integrity',{}).get('passed')and actor.get('requests',{}).get('stopping_policy_replayed')):
        raise ValueError('Independent actual Actor/native/reset review required')
    if not(native.get('passed')and native.get('native_control_gate_qualified') and native.get('original_applied_search_restored') and native.get('query_integrity_qualified')and typed.get('passed')and typed.get('public_answer_fields')=={'ordered_quantity':'number'}and typed.get('query_output_tokens')==4096):
        raise ValueError('Native and typed public-input proof required')
    c=json.loads((project/'scripts/admin_sales_query/public-contract.json').read_text())
    if c['source_task_id']!=SOURCE or c['answer_fields']!={'ordered_quantity':'number'}or c['init_task_id']!='f06b77b2331bb8209410':
        raise ValueError('Published query contract differs')
    if c!=read(config['public_contract'])or config['source_task_row']['goal']!=c['goal']or config['source_task_row']['runtime_task_id']!=c['task_id']:
        raise ValueError('Published source row differs from exact public contract')
    return ref,config,c

def prepare_sales_query_row(task,*,project):
    ref,config,c=registry(project)
    if task.get('source_task_id')!=SOURCE or task.get('task_protocol')!=PROTOCOL or task.get('sales_query_admission')!=ref or task.get('source_row')!=config['source_task_row']:
        raise ValueError('Registered entry differs from current source authority')
    return dict(deepcopy(config['source_task_row']),task_protocol=PROTOCOL,sales_query_admission=ref)

def sales_query_admission(row,project):
    ref,config,c=registry(project)
    expected=dict(config['source_task_row'],task_protocol=PROTOCOL,sales_query_admission=ref)
    if row!=expected:
        raise ValueError('Source-bound query admission differs')
    binding=dict(source_task_id=SOURCE,runtime_task_id=c['task_id'],goal=c['goal'],start_path=c['start_path'],
        answer_fields=c['answer_fields'],spec=dict(kind=PROTOCOL,initial_ui_steps=c['initial_ui_steps']),task_revision=c['task_revision'])
    return dict(passed=True,binding=binding,original_controls_replayed=False,retained_native_controls_verified=True,training_admitted=False)

def run_sales_query(row,project,site,directory,settings,backend):
    from lab_generate_skill.io_utils import atomic_write_json as save
    from lab_generate_skill.admin_pilot import render_task
    directory=Path(directory)
    if not(directory/'attempt-started.json').is_file():raise ValueError('Ordinary batch attempt claim required')
    sales_query_admission(row,project);_,_,c=registry(project)
    module=importlib.import_module('admin_sales_query.ordinary_actor')
    expected=Path(project).resolve()/'scripts/admin_sales_query/ordinary_actor.py'
    if Path(module.__file__).resolve()!=expected:raise ValueError('Query Actor module belongs to another runtime')
    result=module.run_one(site,directory/'native-sales-query',c,settings,backend)
    registry(project)
    trace=json.loads((directory/'native-sales-query/trajectory.json').read_text())
    invalid=sum(not m.get('action_payload')for m in trace['messages']if m['role']=='assistant')
    result.update(task_id=SOURCE,goal=c['goal'],invalid_generations=invalid,
        codebase_status='requires_diagnosis'if trace.get('error')or result['evaluation']['status']=='unknown'or invalid else'interface_exercised',
        trajectory='native-sales-query/trajectory.json')
    save(directory/'result.json',result);render_task(directory,result)
    if trace.get('error')or result['evaluation']['status']=='unknown':raise RuntimeError('Query runtime/evidence failure remains unscored')
    return result
