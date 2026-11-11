"""Reviewed enabled-rule query in the ordinary shared-model Admin entry."""
from pathlib import Path
from copy import deepcopy
import hashlib,importlib,json,sys
SOURCE='da9f45b19b82ff5bd367'
VERSION='source-bound-native-enabled-rule-query-v184'
PROTOCOL='native_enabled_rule_query'

def read(ref):
    if not isinstance(ref,dict)or set(ref)!={'path','sha256'}:raise ValueError('Exact evidence pin required')
    path=Path(ref['path'])
    if not path.is_absolute()or path.is_symlink()or not path.is_file():raise ValueError('Absolute regular evidence required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Reviewed evidence changed: '+str(path))
    return json.loads(raw)

def is_rule_query_source(row):
    return row.get('source_task_id')==SOURCE or row.get('task_protocol')==PROTOCOL or 'rule_query_admission'in row

def rule_query_fixture_source(source,ordinary_fixture):
    return None if source==SOURCE else ordinary_fixture(source)

def registry(project):
    project=Path(project).resolve();runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    ref=runtime.get('reviewed_admin_rule_query');config=read(ref)
    if config.get('version')!=VERSION or config.get('source_task_id')!=SOURCE:raise ValueError('Exact enabled-rule source required')
    compat=read(config['compatibility_review'])
    if not compat.get('passed')or compat.get('candidate_files')!=config.get('candidate_files')or compat.get('first_actor_review')!=config.get('first_actor_review'):
        raise ValueError('Current runtime compatibility proof required')
    expected={'src/lab_generate_skill/admin_rule_query_current.py','scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'}
    if set(compat.get('dispatch_files',{}))!=expected:raise ValueError('Complete ordinary dispatch required')
    files={**config['candidate_files'],**compat['dispatch_files'],**compat['unchanged_execution_dependencies']}
    for name,digest in files.items():
        path=project/name
        if Path(name).is_absolute()or '..'in Path(name).parts or path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Current enabled-rule execution bytes changed: '+name)
        if runtime['actor_submission']['files_sha256'].get(name)!=digest:raise ValueError('Unfrozen current execution file')
    actor=read(config['first_actor_review']);native=read(config['native_input_review']);typed=read(config['typed_input_review'])
    if not(actor.get('passed')and actor.get('source_task_id')==SOURCE and actor.get('status')in('success','failure')and actor.get('job_id')==config['first_actor_job']and actor.get('actual_first_actor_reviewed')and actor.get('full_reset_verified')and actor.get('query_integrity',{}).get('passed')and actor.get('requests',{}).get('stopping_policy_replayed')):
        raise ValueError('Independent actual Actor/native/reset review required')
    if not(native.get('passed')and native.get('source21_interface_visibility_accepted')and typed.get('passed')and typed.get('public_answer_fields')=={'customer_groups':'text_list'}and typed.get('query_output_tokens')==4096):
        raise ValueError('Native and typed public-input proof required')
    c=json.loads((project/'scripts/admin_rule_query/public-contract.json').read_text())
    if c['source_task_id']!=SOURCE or c['answer_fields']!={'customer_groups':'text_list'}or c['init_task_id']is not None:
        raise ValueError('Published query contract differs')
    if c!=read(config['public_contract'])or config['source_task_row']['goal']!=c['goal']or config['source_task_row']['runtime_task_id']!=c['task_id']:
        raise ValueError('Published source row differs from exact public contract')
    return ref,config,c

def prepare_rule_query_row(task,*,project):
    ref,config,c=registry(project)
    if task.get('source_task_id')!=SOURCE or task.get('task_protocol')!=PROTOCOL or task.get('rule_query_admission')!=ref or task.get('source_row')!=config['source_task_row']:
        raise ValueError('Registered entry differs from current source authority')
    return dict(deepcopy(config['source_task_row']),task_protocol=PROTOCOL,rule_query_admission=ref)

def rule_query_admission(row,project):
    ref,config,c=registry(project)
    expected=dict(config['source_task_row'],task_protocol=PROTOCOL,rule_query_admission=ref)
    if row!=expected:
        raise ValueError('Source-bound query admission differs')
    binding=dict(source_task_id=SOURCE,runtime_task_id=c['task_id'],goal=c['goal'],start_path=c['start_path'],
        answer_fields=c['answer_fields'],spec=dict(kind=PROTOCOL,initial_ui_steps=c['initial_ui_steps']),task_revision=c['task_revision'])
    return dict(passed=True,binding=binding,original_controls_replayed=False,retained_native_controls_verified=True,training_admitted=False)

def run_rule_query(row,project,site,directory,settings,backend):
    from lab_generate_skill.io_utils import atomic_write_json as save
    from lab_generate_skill.admin_pilot import render_task
    directory=Path(directory)
    if not(directory/'attempt-started.json').is_file():raise ValueError('Ordinary batch attempt claim required')
    rule_query_admission(row,project);_,_,c=registry(project)
    module=importlib.import_module('admin_rule_query.ordinary_actor')
    expected=Path(project).resolve()/'scripts/admin_rule_query/ordinary_actor.py'
    if Path(module.__file__).resolve()!=expected:raise ValueError('Query Actor module belongs to another runtime')
    result=module.run_one(site,directory/'native-rule-query',c,settings,backend)
    registry(project)
    trace=json.loads((directory/'native-rule-query/trajectory.json').read_text())
    invalid=sum(not m.get('action_payload')for m in trace['messages']if m['role']=='assistant')
    result.update(task_id=SOURCE,goal=c['goal'],invalid_generations=invalid,
        codebase_status='requires_diagnosis'if trace.get('error')or result['evaluation']['status']=='unknown'or invalid else'interface_exercised',
        trajectory='native-rule-query/trajectory.json')
    save(directory/'result.json',result);render_task(directory,result)
    if trace.get('error')or result['evaluation']['status']=='unknown':raise RuntimeError('Query runtime/evidence failure remains unscored')
    return result
