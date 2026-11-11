"""Original physical caller for one source-only qualification, before its claim.

This owns no run plan, task execution, model or training right. Source suppliers
restrict effects to their exact declaration and original attempt; the later
claim authority independently reads the completed measured source and closure.
"""

import os
import threading
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalSourceQualificationOwner:
    def __init__(
        self,
        scope: StateScope,
        execution: SlurmExecutionIdentity,
        controller: SlurmCgroupMembership,
        evidence: EvidenceStore,
    ) -> None:
        self.scope = StateScope.model_validate(scope)
        self.execution = SlurmExecutionIdentity.model_validate(execution)
        self.controller = SlurmCgroupMembership.model_validate(controller)
        if evidence is None:
            raise TypeError("Controlled original source evidence is mandatory")
        self.evidence = evidence
        self._context = os.getpid(), threading.get_ident()
        self._sealed = False
        if (
            self.scope.owner.job_id != self.execution.job_id
            or self.execution.job_id != self.execution.raw_job_id
            or self.controller.job_id != self.execution.raw_job_id
            or self.controller.step_id != "batch"
            or self.controller.uid != self.execution.uid
            or self.scope.task.split != "train"
        ):
            raise OwnershipConflict(
                "Source qualification changed original owner/job/train scope"
            )

    def require_caller(self, op: OperationContext, control: OperationControl) -> None:
        op = OperationContext.model_validate(op)
        control.checkpoint()
        if (
            self._context != (os.getpid(), threading.get_ident())
            or (op.run_id, op.owner_id)
            != (self.scope.owner.run_id, self.scope.owner.owner_id)
            or op.attempt_id not in (None, self.scope.attempt_id)
            or os.getresuid() != (self.execution.uid,) * 3
            or current_process_identity() != self.controller.writer
            or observe_process_cgroup(
                self.execution, self.controller.writer, control
            ).membership
            != self.controller
        ):
            raise OwnershipConflict(
                "Source qualification escaped original physical caller"
            )
        control.checkpoint()

    def require(
        self, op: OperationContext, control: OperationControl, *, new_work: bool
    ) -> None:
        self.require_caller(op, control)
        if new_work and (self._sealed or op.mode != "execute"):
            raise OwnershipConflict("Closed source qualification cannot admit new work")

    def seal(self, op: OperationContext, control: OperationControl) -> None:
        self.require_caller(op, control)
        self._sealed = True
