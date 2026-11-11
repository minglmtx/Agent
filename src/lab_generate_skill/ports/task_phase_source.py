"""Original source reads and live resource rights for shared task phase checks."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.state_scope import StateScope
from .lifecycle import OperationControl


class TaskPhaseSources(Protocol):
    def read(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskPhaseSourceState: ...
    def verify_run(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        run: RunPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...


class TaskPhaseResourceAuthority(Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        read: OperationContext,
        control: OperationControl,
    ) -> None: ...


class TaskPhaseResourceRead(Protocol):
    """Transient facts for one admission, never a reusable permission."""

    @property
    def state(self) -> TaskPhaseSourceState: ...

    def verify(
        self, snapshot: RunSnapshot, reset: ResetPlan, control: OperationControl
    ) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class TaskPhaseResourceReads(Protocol):
    def read_for_admission(
        self,
        plan: TaskExecutionPlan,
        read: OperationContext,
        control: OperationControl,
        *,
        sources: TaskPhaseSources,
    ) -> TaskPhaseResourceRead: ...


@runtime_checkable
class TaskPhaseResourceRechecks(Protocol):
    def recheck(self, control: OperationControl) -> TaskPhaseSourceState:
        """Recheck current source rights at return using this admission's bodies."""
        ...


class TaskOriginSourceProof(Protocol):
    """Reverify original full business source, without site/model effects."""

    def verify_source(self, operation: OperationContext) -> TaskPhaseSourceState: ...


@runtime_checkable
class TaskOriginContextSourceProof(Protocol):
    """Current full source proof also identifies its original public context."""

    def verify_source_context(
        self, operation: OperationContext
    ) -> tuple[TaskPhaseSourceState, StateScope]: ...


class TaskPhaseRunSources(TaskPhaseSources, Protocol):
    """The full RunPlan already verified by this same source read.

    The value is immutable evidence only; a consumer must still check its live
    caller, durable claim and current run journal on every invocation.
    """

    def read_with_run(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[TaskPhaseSourceState, RunPlan]: ...


class TaskPhaseRunRead(Protocol):
    @property
    def state(self) -> TaskPhaseSourceState: ...
    @property
    def run(self) -> RunPlan: ...
    def recheck(self, control: OperationControl) -> TaskPhaseSourceState: ...
    def close(self) -> None: ...


@runtime_checkable
class TaskPhaseClaimRead(Protocol):
    @property
    def claim(self) -> SourceClaimReceipt | None:
        """Complete claim from this open source proof, never an authority grant."""
        ...


@runtime_checkable
class TaskPhaseOwnershipReads(Protocol):
    def read_ownership(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[TaskPhaseSourceState, RunPlan, SourceClaimReceipt] | None:
        """Original source's immutable run/claim bodies with fresh storage gates.

        The receiving owner must still check its actual claim ledger, caller
        and run journal. None preserves the legacy complete-reading path.
        """
        ...


@runtime_checkable
class TaskPhaseRunReads(Protocol):
    def open_run_read(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskPhaseRunRead:
        """One graph including RunPlan; current rights stay with the original reader."""
        ...
