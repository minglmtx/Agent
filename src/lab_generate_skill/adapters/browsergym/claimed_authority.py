"""Claim-bound original browser permission; actual CPU identity and closure facts.

PreparedBrowserAuthority supplies original preparation checks. The existing
registered-browser supervisor owns physical stop and its retained kernel proof;
this supplier never starts, signals, retries or substitutes a page/session.
"""

from typing import Literal
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl


class ClaimedBrowserResourceAuthority:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        spec: BrowserResourceSpec,
        acquisition: OperationContext,
    ) -> None:
        if not isinstance(owner, ClaimedRunResourceOwner):
            raise TypeError("Original claimed execution owner required")
        self.owner, self.spec, self.acquisition = (
            owner,
            BrowserResourceSpec.model_validate(spec),
            OperationContext.model_validate(acquisition),
        )
        self.spec.check_operation(self.acquisition, "execute")
        if (
            self.spec.token.owner != owner.run.owner
            or self.spec.configuration.spec.task.identity != owner.task.identity
            or self.spec.slurm.execution != owner.authority.execution
            or self.spec.slurm.parent != owner.authority.controller
        ):
            raise OwnershipConflict("Browser changed original claimed task/controller")
        self.started: BrowserResourceStarted | None = None
        self.start_attempted = self.closing = self.close_attempted = False

    def _require(
        self, op: OperationContext, control: OperationControl, *, cleanup: bool
    ) -> None:
        self.spec.check_operation(op, "cleanup" if cleanup else "execute")
        if cleanup and op.parent_operation_id != self.acquisition.operation_id:
            raise OwnershipConflict(
                "Browser cleanup changed original acquisition parent"
            )
        if not cleanup and self.closing:
            raise OwnershipConflict("Closing original browser cannot admit new work")
        self.owner.require(op, control, new_work=not cleanup)
        if not cleanup:
            inputs = self.owner.task_source(op, control)
            if self.spec.token.attempt_id != inputs.intent.binding.attempt_id:
                raise OwnershipConflict(
                    "Browser changed original single source attempt"
                )
        if self.started is not None and not cleanup:
            target = self.started.step.controller.target
            if (
                observe_process_cgroup(
                    self.spec.slurm.execution, self.started.owner_guard.worker, control
                ).membership
                != target.worker
            ):
                raise OwnershipConflict("Original browser worker/cgroup changed")

    def authorize_start(
        self, spec: BrowserResourceSpec, op: OperationContext, control: OperationControl
    ) -> None:
        if spec != self.spec or op != self.acquisition or self.start_attempted:
            raise OwnershipConflict("Original browser acquisition is one-shot")
        self.owner.caller(op, control)
        self.start_attempted = True
        self._require(op, control, cleanup=False)

    def verify(
        self,
        spec: BrowserSessionSpec,
        phase: Literal["start", "step", "close"],
        action: BrowserAction | None,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        if spec != self.spec.configuration.spec:
            raise OwnershipConflict("Browser command changed original public session")
        cleanup = phase == "close"
        self._require(op, control, cleanup=cleanup)
        if cleanup:
            self.closing = True
        elif not self.start_attempted or (
            phase == "step"
            and (
                self.started is None
                or action is None
                or action.name not in spec.task.allowed_actions
            )
        ):
            raise OwnershipConflict(
                "Original initialized browser and allowed action required"
            )

    def verify_started(
        self,
        spec: BrowserResourceSpec,
        started: BrowserResourceStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._require(op, control, cleanup=False)
        target = started.step.controller.target
        if (
            spec != self.spec
            or op != self.acquisition
            or self.started is not None
            or started.owner_guard.controller != spec.slurm.parent.writer
            or target.execution != spec.slurm.execution
            or target.worker.writer != started.owner_guard.worker
        ):
            raise OwnershipConflict(
                "Browser initialization replaced original acquired worker"
            )
        if (
            observe_process_cgroup(
                spec.slurm.execution, started.owner_guard.worker, control
            ).membership
            != target.worker
        ):
            raise OwnershipConflict(
                "Original browser worker was not independently observed"
            )
        self.started = BrowserResourceStarted.model_validate(started)

    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        op: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        if spec != self.spec or self.close_attempted:
            raise OwnershipConflict("Original browser close admission is one-shot")
        self.spec.check_operation(op, "cleanup")
        if op.parent_operation_id != self.acquisition.operation_id:
            raise OwnershipConflict(
                "Browser cleanup changed original acquisition parent"
            )
        self.owner.caller(op, control)
        self.close_attempted = self.closing = True
        self._require(op, control, cleanup=True)
        if termination is None or termination.cleanup_errors:
            raise OwnershipConflict("Original browser termination is unconfirmed")
        if termination.state == "not_started":
            raise OwnershipConflict(
                "Non-start requires independent original no-registration proof"
            )
        if (
            termination.state != "reaped"
            or termination.process_id != attempt.launcher_pid
            or step is None
            or step.target != attempt.target
            or (self.started is not None and attempt.started != self.started)
        ):
            raise OwnershipConflict("Original complete browser domain closure required")
        if (
            step.quiescence.original != step.target.worker
            or step.quiescence.writer_status not in ("missing", "reused")
        ):
            raise OwnershipConflict("Browser closure changed original worker identity")
        WorkerStepEvidence("browser").require(
            self.owner.evidence, step.evidence, step.target, "closed", control
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=op.operation_id,
            status="closed",
            evidence=(step.evidence,),
        )
