"""Original lifecycle seams over existing site/browser/state/Actor capabilities.

No default implementation or permission. The composition root binds actual
registered resources, original task operations and existing capture selectors.
Batch model/site resources remain with their outer scope, not per-attempt reset.
"""

from typing import Protocol
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    TaskCaptureResult,
    ClosedTaskResources,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .actor import ActorRunner
from .lifecycle import OperationControl


class TaskPreparation(Protocol):
    def acquire(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        """Acquire only new attempt resources once, or bind explicitly held
        original batch resources. Never reacquire an existing/unknown resource;
        batch ownership remains with its original outer scope.
        """
        ...

    def prepare(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[EvidenceRef, ...]:
        """Commit original recovery/snapshot before preparation effects; no retry."""
        ...


class TaskInitialization(Protocol):
    def start(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitializedTask:
        """Original browser start, unique public initial observation, complete
        baseline and measured candidate equivalence. Never reuse source as a new
        observation or execute Actor here. Existing leaf authorities mandatory.
        """
        ...


class TaskCapture(Protocol):
    def preflight(
        self,
        plan: TaskExecutionPlan,
        requirements: EvidenceRequirements,
        control: OperationControl,
    ) -> None: ...
    def capture(
        self,
        plan: TaskExecutionPlan,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskCaptureResult:
        """Use original eligible terminal selector, SiteCapture and fixed worker.
        No eligible request means no DB query; no duplicate/unknown redispatch.
        Preserve full original response/files and native HTTP/union distinction.
        """
        ...


class TaskFinalization(Protocol):
    def close(
        self,
        plan: TaskExecutionPlan,
        reset: ResetPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosedTaskResources:
        """Always inspect/close original registered resources, including partial
        initialization. Actual termination/closure authority mandatory; returning
        data alone cannot establish closure. Unknown closure refuses restoration.
        """
        ...

    def restore(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> EvidenceRef:
        """Original full restore/necessary resume/health/safe Reset; no retries.
        Return original reset-receipt for independent StateRecords verification.
        Preserve unsafe state/quarantine and all errors; never reset before close.
        """
        ...


class TaskClosureAuthority(Protocol):
    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Independently check original resource journal and native termination,
        not just shape/status of caller-supplied closure objects.
        """
        ...


class TaskActorBinding(Protocol):
    def bind(
        self, initialized: InitializedTask, prepared: PreparedActorInput
    ) -> ActorRunner:
        """Bind the existing ActorRunner to original acquired model/browser;
        no start/reset/model calls during binding, no alternative runner.
        """
        ...
