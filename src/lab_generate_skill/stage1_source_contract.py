"""Prospective source/contract construction; no historical identity correction.

Trusted callers supply the Admin functions from their frozen executable runtime.
The returned data grants no claim, live execution, checkpoint import or export.
"""
from .stage1_evaluator_binding import (
    corrected_source, require, require_declared_evaluator, resolve_admitted_admin,
)


def prepare_admin_source(source, *, public_goal, bind, actor_goal):
    """Resolve a fresh source before its initial-state qualification is frozen."""
    require(not {'checkpoint', 'checkpoint_mode', 'initial_qualification'} & source.keys(),
            'Prospective preparation must precede qualification or checkpoint binding')
    resolution = resolve_admitted_admin(source, bind=bind, actor_goal=actor_goal)
    require(resolution['public_goal'] == public_goal, 'Registered training goal differs from admitted goal')
    return corrected_source(source, resolution)


def build_local_contract(source, *, public_goal, website_snapshot_id,
                         runtime_capsule_sha256, output_purpose, teacher_mode,
                         bind=None, actor_goal=None):
    """Validate declared identity before constructing a new exact contract.

    A wrong declaration is rejected, never silently rewritten. Formal contracts
    still require NativeTrainingValidator and its independent release checks.
    """
    require((output_purpose, teacher_mode) in {
        ('engineering_pilot', 'local_replacement'), ('training', 'authorized_api'),
    }, 'Unsupported source contract purpose')
    if source['domain'] == 'shopping_admin':
        require(callable(bind) and callable(actor_goal), 'Trusted frozen Admin callbacks required')
        resolution = resolve_admitted_admin(source, bind=bind, actor_goal=actor_goal)
        require(resolution['public_goal'] == public_goal, 'Registered training goal differs from admitted goal')
        require_declared_evaluator(source, resolution)
        evaluator_version = resolution['evaluator_version']
    else:
        require(bind is None and actor_goal is None, 'Admin callbacks supplied for another domain')
        evaluator_version = source['evaluator_version']
    result = dict(version='local-stage1-contract-v1', task_id=source['active_task_id'],
        source_task_id=source['source_task_id'], runtime_task_id=source['runtime_task_id'],
        domain=source['domain'], public_goal=public_goal, website_snapshot_id=website_snapshot_id,
        runtime_capsule_sha256=runtime_capsule_sha256, evaluator_version=evaluator_version,
        output_purpose=output_purpose, teacher_mode=teacher_mode)
    require(all(isinstance(v, str) and bool(v.strip()) for v in result.values()),
            'Source contract has an empty or non-string field')
    return result
