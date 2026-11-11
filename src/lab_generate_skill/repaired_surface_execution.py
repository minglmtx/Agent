"""Source-scoped current readers for immutable repaired-surface producer bytes."""
from copy import deepcopy
from pathlib import Path
import hashlib,importlib
from . import reviewed_code_evolution


def binding_changes(original,current,package='map_surfaces',*,route_additions=None):
    if not isinstance(original,dict)or not isinstance(current,dict)or original.keys()!=current.keys():
        raise ValueError('Exact original surface execution field inventory required')
    groups={'candidate_modules','runtime_modules'}
    nested={'shared_route_lifecycle'}if package=='map_surfaces'else set()
    if any(original[k]!=current[k]for k in original.keys()-groups-nested):
        raise ValueError('Original contract, renderer or non-code execution binding changed')
    result=[]
    for group in sorted(groups):
        a,b=original[group],current[group]
        if not isinstance(a,dict)or not isinstance(b,dict):raise ValueError('Explicit execution module inventories required')
        additions=route_additions if package=='map_routes'and group=='candidate_modules'else None
        if additions is not None:
            if set(additions)!={'retained_first_cycle.py','retained_phase.py'}or set(b)-set(a)!=set(additions)or set(a)-set(b)or any(b[k]!=v for k,v in additions.items()):
                raise ValueError('Only the exact separately reviewed retained-route readers may be added')
            result.extend((package,group,name,None,b[name])for name in sorted(additions))
        elif a.keys()!=b.keys():raise ValueError('Original execution module inventory must remain exact')
        for name in sorted(a):
            if a[name]!=b[name]:result.append((package,group,name,a[name],b[name]))
    if nested:result+=binding_changes(original['shared_route_lifecycle'],current['shared_route_lifecycle'],'map_routes',route_additions=route_additions)
    return result


def bind(owner,current):
    original=owner.config['execution_binding']
    if original==current:return deepcopy(current)
    scoped=reviewed_code_evolution.scope(owner)
    if scoped is None:raise ValueError('Explicit source-scoped surface code review required')
    config,review,rows=scoped
    additions=review.get('surface_added_route_modules')
    changes=binding_changes(original,current,route_additions=additions)
    if not changes:raise ValueError('Unexplained surface execution binding change')
    if set(config['source_ids'])!=set(owner.config['source_ids']):raise ValueError('Surface review source coverage differs')
    project=Path(owner.project).resolve()
    if Path(__file__).resolve()!=project/'src/lab_generate_skill/repaired_surface_execution.py':
        raise ValueError('Surface binding reader must belong to frozen current project')
    owner.track(Path(__file__))
    for package,group,name,old,new in changes:
        if group=='candidate_modules':
            if Path(name).name!=name or not name.endswith('.py'):raise ValueError('Regular candidate Python file required')
            path=project/'scripts'/package/name
        else:path=Path(importlib.import_module(name).__file__).resolve()
        try:relative=path.relative_to(project).as_posix()
        except ValueError:raise ValueError('Surface runtime dependency escaped current project')
        if not relative.endswith('.py')or not relative.startswith(('scripts/','src/lab_generate_skill/'))or path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=new:
            raise ValueError('Actual current surface dependency differs')
        matches=[r for r in rows if r['path']==relative and r['old_sha256']==old and r['current_sha256']==new and r.get('remaining_ast_identical')is True]
        if len(matches)!=1:raise ValueError('Surface dependency has no exact reviewed code delta')
        owner.track(path)
    return deepcopy(current)


def require_input_reader(owner,current,producer,candidates):
    from .remaining_surface_catalog import RemainingSurfaceCatalog
    from .map_route_normal_capture import fingerprint
    if type(owner)is not RemainingSurfaceCatalog or owner.closed or owner.config.get('repaired_phase')is not True:
        raise ValueError('Open current repaired-surface catalog required')
    if owner.execution_binding!=producer or owner.config['execution_binding']!=producer:
        raise ValueError('Different original surface input producer')
    owner.require_current()
    if bind(owner,current)!=owner.current_execution_binding:raise ValueError('Current surface reader changed')
    scoped=reviewed_code_evolution.scope(owner)
    if scoped is None:raise ValueError('Exact surface source review required')
    _,review,_=scoped
    if [c['source_task_id']for c in candidates]!=owner.config['source_ids']or any(review['candidate_sha256'].get(c['source_task_id'])!=fingerprint(c)for c in candidates):
        raise ValueError('Surface source definition changed from reviewed input')
