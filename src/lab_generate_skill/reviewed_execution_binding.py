"""Keep producer bindings immutable while validating explicitly reviewed code.

Raw archive readers still receive the producer's original execution binding.
This check returns the actual current binding separately. It accepts only exact
Python deltas in the registry's existing source-scoped code-evolution review;
contract digests, module inventories and other binding fields remain exact.
"""
from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
from . import reviewed_code_evolution

PACKAGES={
    'remaining-route-full-proof-catalog-v1':'map_routes',
    'route-device-location-full-proof-catalog-v1':'map_route_location',
}

def require_binding(owner,current):
    original=owner.config['execution_binding']
    if original==current:return deepcopy(current)
    package=PACKAGES.get(owner.config.get('version'))
    if package is None:raise ValueError('Unreviewed execution-binding family')
    if set(original)!=set(current):raise ValueError('Execution-binding field inventory changed')
    modules={'candidate_modules','runtime_modules'}
    if any(original[k]!=current[k]for k in original.keys()-modules):
        raise ValueError('Source contract or execution semantics changed')
    scoped=reviewed_code_evolution.scope(owner)
    if scoped is None:raise ValueError('Changed execution bytes require explicit source-scoped review')
    config,review,rows=scoped
    if set(config['source_ids'])!=set(owner.config['source_ids']):
        raise ValueError('Execution-binding review source coverage differs')
    project=Path(owner.project).resolve()
    if Path(__file__).resolve()!=project/'src/lab_generate_skill/reviewed_execution_binding.py':
        raise ValueError('Execution-binding reader must belong to current frozen project')
    owner.track(Path(__file__))
    changes=[]
    for group in sorted(modules):
        a,b=original[group],current[group]
        if set(a)!=set(b):raise ValueError('Execution module additions/removals require a separate reviewed closure')
        for name in sorted(a):
            if a[name]==b[name]:continue
            if group=='candidate_modules':
                if Path(name).name!=name or not name.endswith('.py'):
                    raise ValueError('Regular Python candidate module required')
                rel='scripts/'+package+'/'+name;path=project/rel
            else:
                module=importlib.import_module(name);path=Path(module.__file__).resolve()
                try:rel=path.relative_to(project).as_posix()
                except ValueError:raise ValueError('Execution runtime module is outside frozen project')
                if not rel.endswith('.py')or not rel.startswith(('src/lab_generate_skill/','scripts/')):
                    raise ValueError('Only frozen Python runtime changes may be reviewed')
            if path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=b[name]:
                raise ValueError('Current execution module bytes differ')
            matches=[r for r in rows if r['path']==rel and r['old_sha256']==a[name]and r['current_sha256']==b[name]
                     and r.get('remaining_ast_identical')is True]
            if len(matches)!=1:raise ValueError('Execution delta lacks an exact source-scoped code review')
            owner.track(path);changes.append(rel)
    if not changes:raise ValueError('Unexplained execution-binding difference')
    return deepcopy(current)


def require_candidates(owner,candidates):
    if owner.config.get('_code_evolution')is None:return
    _,review,_=reviewed_code_evolution.scope(owner)
    from .map_route_normal_capture import fingerprint
    rows=list(candidates)
    if {c['source_task_id']for c in rows}!=set(owner.config['source_ids']):
        raise ValueError('Execution review candidate coverage differs')
    if any(review['candidate_sha256'].get(c['source_task_id'])!=fingerprint(c)for c in rows):
        raise ValueError('Execution review source definition changed')


def require_producer(owner,current,producer,candidates):
    """Authorize a historical raw reader only inside its verified catalog.

    The producer binding is never substituted: all archive/control/input checks
    continue to compare against it. The current reader has a separate complete
    source-scoped code review, valid for exactly these candidates/configuration.
    """
    from map_routes.catalog import RemainingRouteCatalog
    if not isinstance(owner,RemainingRouteCatalog)or owner.closed:
        raise ValueError('An open reviewed source catalog must own historical replay')
    if producer!=owner.execution_binding or producer!=owner.config['execution_binding']:
        raise ValueError('Raw replay belongs to another producer binding')
    owner.require_current()
    if require_binding(owner,current)!=owner.current_execution_binding:
        raise ValueError('Raw replay current reader differs from reviewed execution')
    require_candidates(owner,candidates)
