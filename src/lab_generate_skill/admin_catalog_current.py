"""Explicit native CSV admission in the shared-model ordinary Admin batch.

The eleven native modules are copied exactly from the executed first Actor.
This module only validates their source and dispatches their existing episode.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys

SOURCE='986fe7a818c13d647950'
VERSION='source-bound-native-admin-catalog-v1'
FILES=frozenset('scripts/admin_catalog/'+n for n in (
    'catalog_baseline.py','catalog_csv.py','catalog_environment.py','catalog_episode.py',
    'catalog_evaluator.py','catalog_private.php','catalog_protection.py','catalog_service.py',
    'input_control.py','intake.py','ordinary_actor.py'))


def _read(ref):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:
        raise ValueError('Exact CSV evidence pin required')
    p=Path(ref['path'])
    if not p.is_absolute() or p.is_symlink() or not p.is_file():
        raise ValueError('Absolute regular CSV evidence required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('CSV evidence changed: '+str(p))
    return json.loads(raw)


def is_catalog_source(row):
    return (row.get('source_task_id')==SOURCE or row.get('task_protocol')=='native_catalog_csv'
            or 'catalog_admission' in row)


def catalog_fixture_source(source, ordinary_fixture):
    return None if source==SOURCE else ordinary_fixture(source)


def _registry(project):
    project=Path(project).resolve()
    runtime=json.loads((project/'configs/site-runtime-current.json').read_text())
    ref=runtime.get('reviewed_admin_catalog')
    config=_read(ref)
    if config.get('version')!=VERSION or config.get('source_task_id')!=SOURCE:
        raise ValueError('Exact published CSV source required')
    pins=config.get('candidate_files',{})
    if set(pins)!=FILES:
        raise ValueError('Complete tested native CSV package required')
    capsule=_read(config['executed_capsule'])
    for name,digest in pins.items():
        path=project/name
        if (path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest
                or capsule['members'][name]['sha256']!=digest
                or runtime['actor_submission']['files_sha256'].get(name)!=digest):
            raise ValueError('Current CSV native code differs from executed source')
    for name in ('src/lab_generate_skill/admin_catalog_current.py',
                 'scripts/run_registered_admin_batch.py','scripts/run_archived_admin_actor.py'):
        if hashlib.sha256((project/name).read_bytes()).hexdigest()!=runtime['actor_submission']['files_sha256'].get(name):
            raise ValueError('Current CSV dispatch code is not frozen')
    review=_read(config['first_actor_review'])
    if (review.get('passed') is not True or review.get('source_task_id')!=SOURCE
            or review.get('first_actor_attempts')!=1 or review.get('status') not in ('success','failure')
            or review.get('runtime_error') is not None or review.get('paid_api_calls')!=0):
        raise ValueError('Independently reviewed first ordinary Actor required')
    candidate=project/'scripts/admin_catalog'
    # The executed candidate uses sibling imports. Fail on an existing foreign
    # module rather than replacing another runtime's imported implementation.
    for name in FILES:
        if not name.endswith('.py'):continue
        module=sys.modules.get(Path(name).stem)
        if module is not None and Path(module.__file__).resolve()!=project/name:
            raise ValueError('Native CSV module namespace already belongs to another project')
    if str(candidate) not in sys.path:sys.path.insert(0,str(candidate))
    intake=importlib.import_module('intake'); actor=importlib.import_module('ordinary_actor')
    if Path(intake.__file__).resolve()!=candidate/'intake.py' or Path(actor.__file__).resolve()!=candidate/'ordinary_actor.py':
        raise ValueError('Actual frozen CSV modules required')
    from .public_interface_intake import catalog_class
    return ref,config,catalog_class(intake.CatalogIntake,config,project),actor.run_one


@contextmanager
def current_intake(row, project):
    ref,config,Intake,run_one=_registry(project)
    expected={**config['source_task_row'],'task_protocol':'native_catalog_csv','catalog_admission':ref}
    if row!=expected or expected['source_task_id']!=SOURCE:
        raise ValueError('CSV public source row or current admission differs')
    with Intake(config['intake'],project=project,candidate=Path(project)/'scripts/admin_catalog') as intake:
        contract=_read(config['public_contract'])
        if intake.public_task!=contract or row['goal']!=contract['goal'] or row['runtime_task_id']!=contract['task_id']:
            raise ValueError('Executed CSV public definition changed')
        intake.require_current()
        yield intake,run_one
        intake.require_current()


def prepare_catalog_row(task, *, project):
    ref,config,_,_=_registry(project)
    if (task.get('source_task_id')!=SOURCE or task.get('task_protocol')!='native_catalog_csv'
            or task.get('catalog_admission')!=ref or task.get('source_row')!=config['source_task_row']):
        raise ValueError('Registered CSV entry differs from current source authority')
    row={**deepcopy(config['source_task_row']),'task_protocol':'native_catalog_csv','catalog_admission':ref}
    with current_intake(row,project):pass
    return row


def catalog_admission(row, project):
    with current_intake(row,project) as (intake,_):
        c=intake.public_task
        binding=dict(source_task_id=c['source_task_id'],runtime_task_id=c['task_id'],goal=c['goal'],
            start_path=c['start_path'],status='ready_for_single_attempt',scope_id=0,
            spec=dict(kind='native_catalog_csv',mode='export'),task_revision=c['task_revision'])
        return dict(passed=True,binding=binding,original_controls_replayed=True,training_admitted=False)


def run_catalog(row, project, site, directory, settings, backend):
    from lab_generate_skill.io_utils import atomic_write_json as save
    from lab_generate_skill.admin_pilot import render_task
    directory=Path(directory)
    if not (directory/'attempt-started.json').is_file():
        raise ValueError('Ordinary batch must claim this attempt first')
    with current_intake(row,project) as (intake,run_one):
        result=run_one(site,directory/'native-catalog',intake.proof['baseline'],intake.public_task,
                       settings,backend,environment=intake.environment)
        trace=json.loads((directory/'native-catalog/trajectory.json').read_text())
        invalid=sum(not m.get('action_payload') for m in trace['messages'] if m['role']=='assistant')
        result.update(task_id=SOURCE,goal=intake.public_task['goal'],invalid_generations=invalid,
            codebase_status='requires_diagnosis' if trace.get('error') or result['evaluation']['status']=='unknown' or invalid else 'interface_exercised',
            trajectory='native-catalog/trajectory.json')
        save(directory/'result.json',result);render_task(directory,result)
        if trace.get('error') or result['evaluation']['status']=='unknown':
            raise RuntimeError('CSV runtime or evidence failure; do not label model failure or continue batch')
        return result
