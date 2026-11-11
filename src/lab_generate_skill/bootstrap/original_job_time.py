"""Bind original job controls to an explicit budget and actual finite hard end.

Used by deployment entries before metadata/resource consumers are created.
Accounting, kernel containment and every dynamic permission remain mandatory at
their original gates; this read and time intersection do not grant them.
"""

from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.job_time import (
    SlurmJobTimeObservation,
    observe_job_time_limit,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls


def original_job_controls(
    execution: SlurmExecutionIdentity,
    owner: ResourceOwner,
    node_id: str,
    budgets: OperationWindowBudgets,
    controls: OperationControls,
    clock: Clock,
    control: OperationControl,
) -> tuple[BoundedOperationControls, SlurmJobTimeObservation]:
    execution = SlurmExecutionIdentity.model_validate(execution)
    owner = ResourceOwner.model_validate(owner)
    budgets = OperationWindowBudgets.model_validate(budgets)
    if owner.job_id != execution.job_id:
        raise OwnershipConflict("Time window owner differs from original job")
    observed = observe_job_time_limit(
        execution, node_id, control, clock, runner=SlurmCommandRunner()
    )
    window = budgets.window(owner, now=clock.utcnow(), hard_end=observed.limit.hard_end)
    return BoundedOperationControls(controls, clock, window), observed
