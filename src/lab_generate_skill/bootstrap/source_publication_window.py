"""Bind closed-source publication to the original caller's execution budget.

This does not extend acquisition, authorize a source, or resume an old job.
The caller supplies its pre-existing root and the same guarded controls; actual
publishers still verify the live original owner and complete recovery evidence.
"""

from datetime import timedelta

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import Clock, OperationControls


def publication_parent(
    acquisition: OperationContext,
    parent: OperationContext | None,
    controls: OperationControls,
) -> OperationContext:
    acquisition = OperationContext.model_validate(acquisition)
    if parent is None:
        return acquisition
    parent = OperationContext.model_validate(parent)
    if (
        parent.mode != "execute"
        or parent.operation_id == acquisition.operation_id
        or (parent.run_id, parent.owner_id, parent.cancellation_ref)
        != (acquisition.run_id, acquisition.owner_id, acquisition.cancellation_ref)
        or parent.attempt_id not in (None, acquisition.attempt_id)
        or parent.allocation_id is not None
        or parent.recovery_ref is not None
        or parent.parent_operation_id is not None
        or parent.deadline < acquisition.deadline
    ):
        raise OwnershipConflict("Publication requires the same original execution root")
    # Register/check the exact original descriptor before any source effect.
    controls.bind(parent).checkpoint()
    return parent


def closed_publication_operation(
    parent: OperationContext,
    operation_id: str,
    metadata_seconds: int,
    controls: OperationControls,
    clock: Clock,
) -> OperationContext:
    if type(metadata_seconds) is not int or not 1 <= metadata_seconds <= 3600:
        raise ValueError("Explicit bounded publication duration required")
    # Global owner window, monotonic guard and original cancellation still apply.
    controls.bind(parent).checkpoint()
    return OperationContext(
        operation_id=operation_id,
        run_id=parent.run_id,
        owner_id=parent.owner_id,
        cancellation_ref=parent.cancellation_ref,
        deadline=min(
            parent.deadline, clock.utcnow() + timedelta(seconds=metadata_seconds)
        ),
    )
