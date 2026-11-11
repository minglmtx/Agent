"""Source-bound Links admission and ordinary shared-model dispatch."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib,importlib,json,sys
from pathlib import Path
SOURCE='680a097ada00b0af5f17'
VERSION='source-bound-native-admin-links-v1'
PACKAGE='scripts/admin_links/'
FILES=frozenset(PACKAGE+n for n in ('__init__.py', 'calendar-review.json', 'evaluator-review.json', 'factory_calendar.py', 'input_control.py', 'interface_control.py', 'links_episode.py', 'links_evaluator.py', 'links_feedback.py', 'links_intake.py', 'native_capture.php', 'native_initial_helpers.py', 'native_snapshot.py', 'observed_control.py', 'ordinary_actor.py', 'original-snapshot.php', 'public-contract.json', 'relocation.py', 'save_http_observer.py', 'source-semantics-review.json'))


def _read(ref):
    if not isinstance(ref,dict)or set(ref)!={'path','sha256'}:raise ValueError('Exact Links evidence pin required')
    p=Path(ref['path'])
    if not p.is_absolute()or p.is_symlink()or not p.is_file():raise ValueError('Absolute regular Links evidence required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Links evidence changed: '+str(p))
    return json.loads(raw)


def is_links_source(row):
    return row.get('source_task_id')==SOURCE or row.get('task_protocol')=='native_product_links' or 'links_admission'in row


def links_fixture_source(source,ordinary_fixture):
    return None if source==SOURCE else ordinary_fixture(source)


def _registry(project):
    project=Path(project).resolve();runtime=json.loads((project/'configs/site-runtime-current.json').read_text());ref=runtime.get('reviewed_admin_links');config=_read(ref)
    if config.get('version')!=VERSION or config.get('source_task_id')!=SOURCE:raise ValueError('Exact published Links source required')
    pins=config.get('candidate_files',{})
    if set(pins)!=FILES:raise ValueError('Complete Links package required')
    for name,digest in pins.items():
        path=project/name
        if path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=digest or runtime['actor_submission']['files_sha256'].get(name)!=digest:raise ValueError('Current Links package differs from reviewed code')
        if name.endswith('.py'):
            module_name='.'.join(Path(name).with_suffix('').parts[1:]);module_name=module_name.removesuffix('.__init__');module=sys.modules.get(module_name)
            if module is not None and Path(module.__file__).resolve()!=path.resolve():raise ValueError('Links module belongs to another project')
    for name in ('src/lab_generate_skill/admin_links_current.py','scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'):
        if hashlib.sha256((project/name).read_bytes()).hexdigest()!=runtime['actor_submission']['files_sha256'].get(name):raise ValueError('Current Links dispatch is not frozen')
    review=_read(config['first_actor_review']);input_review=_read(config['ordinary_input_review']);compat=_read(config['compatibility_review'])
    if (review.get('passed')is not True or review.get('source_task_id')!=SOURCE or review.get('status')not in('success','failure')or review.get('actor_job')!=config['first_actor_job']or not review.get('full369_original_baseline_verified')or not review.get('full369_reset_verified')or not review.get('full927media_reset_verified')or not review.get('request_review',{}).get('stopping_policy_replayed')):raise ValueError('Independently verified ordinary Links execution required')
    if not all(review.get(k)is True for k in ('full369_normalized_baseline_verified','full369_normalized_reset_verified'))or review.get('executed_module_snapshots_verified')!=3 or review.get('native_source_files_verified')!=39 or review.get('first_actor_attempts')!=1:raise ValueError('Verified original and normalized Links evidence and actual module identities required')
    if not input_review.get('passed')or input_review.get('source_task_id')!=SOURCE or not input_review.get('actual_complete_native_three_links_verified')or input_review.get('ordinary_actions')!=39 or not input_review.get('all_action_bids_from_preceding_viewport_ax')or input_review.get('normalized_full369_resets_verified')!=3 or input_review.get('original_full369_and927_resets_verified')!=3:raise ValueError('Independently verified ordinary Links input required')
    if not compat.get('passed')or compat.get('first_actor_review')!=config['first_actor_review']or compat.get('candidate_files')!=pins:raise ValueError('Explicit Links relocation/current-runtime compatibility required')
    expected_dispatch={'src/lab_generate_skill/admin_links_current.py','scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'}
    if set(compat.get('dispatch_files',{}))!=expected_dispatch:raise ValueError('Complete reviewed Links dispatch required')
    for name,digest in compat['dispatch_files'].items():
        if runtime['actor_submission']['files_sha256'].get(name)!=digest or hashlib.sha256((project/name).read_bytes()).hexdigest()!=digest:raise ValueError('Links dispatch differs from compatibility review')
    for name,digest in compat['unchanged_execution_dependencies'].items():
        if runtime['actor_submission']['files_sha256'].get(name)!=digest or hashlib.sha256((project/name).read_bytes()).hexdigest()!=digest:raise ValueError('Links native execution dependency changed: '+name)
    scripts=str(project/'scripts')
    if scripts not in sys.path:sys.path.insert(0,scripts)
    intake=importlib.import_module('admin_links.links_intake');actor=importlib.import_module('admin_links.ordinary_actor')
    if Path(intake.__file__).resolve()!=project/PACKAGE/'links_intake.py' or Path(actor.__file__).resolve()!=project/PACKAGE/'ordinary_actor.py':raise ValueError('Actual current Links modules required')
    return ref,config,intake.LinksIntake,actor.run_one


@contextmanager
def current_intake(row,project):
    ref,config,Intake,run_one=_registry(project);expected={**config['source_task_row'],'task_protocol':'native_product_links','links_admission':ref}
    if row!=expected or row.get('source_task_id')!=SOURCE:raise ValueError('Links source row or admission changed')
    cycles=[]
    for item in config['control_cycles']:
        _read(item['plan']);_read(item['review']);cycles.append(Path(item['plan']['path']).parent)
    intake=Intake(cycles);contract=_read(config['public_contract'])
    if intake.public_task!=contract or row['goal']!=contract['goal']or row['runtime_task_id']!=contract['task_id']:raise ValueError('Links public definition changed')
    intake.require_current()
    try:yield intake,run_one
    finally:intake.require_current()


def prepare_links_row(task,*,project):
    ref,config,_,_=_registry(project)
    if task.get('source_task_id')!=SOURCE or task.get('task_protocol')!='native_product_links' or task.get('links_admission')!=ref or task.get('source_row')!=config['source_task_row']:raise ValueError('Registered Links entry differs from current source authority')
    row={**deepcopy(config['source_task_row']),'task_protocol':'native_product_links','links_admission':ref}
    with current_intake(row,project):pass
    return row


def links_admission(row,project):
    with current_intake(row,project)as(intake,_):
        c=intake.public_task;binding=dict(source_task_id=SOURCE,runtime_task_id=c['task_id'],goal=c['goal'],start_path=c['start_path'],status='ready_for_single_attempt',scope_id=0,spec=dict(kind='native_product_links',mode='native_product_links'),task_revision=dict(kind='derived',source_goal=c['original_goal'],reason=c['derivation_reason']))
        return dict(passed=True,binding=binding,original_controls_replayed=True,training_admitted=False)


def run_links(row,project,site,directory,settings,backend):
    from lab_generate_skill.io_utils import atomic_write_json as save
    from lab_generate_skill.admin_pilot import render_task
    directory=Path(directory)
    if not(directory/'attempt-started.json').is_file():raise ValueError('Ordinary batch must claim this attempt first')
    with current_intake(row,project)as(intake,run_one):
        result=run_one(site,directory/'native-links',intake,settings,backend);trace=json.loads((directory/'native-links/trajectory.json').read_text())
        invalid=sum(not m.get('action_payload')for m in trace['messages']if m['role']=='assistant')
        result.update(task_id=SOURCE,goal=intake.public_task['goal'],invalid_generations=invalid,codebase_status='requires_diagnosis'if trace.get('error')or result['evaluation']['status']=='unknown'or invalid else'interface_exercised',trajectory='native-links/trajectory.json')
        save(directory/'result.json',result);render_task(directory,result)
        if trace.get('error')or result['evaluation']['status']=='unknown':raise RuntimeError('Links runtime or evidence failure; do not label model failure or continue batch')
        return result
