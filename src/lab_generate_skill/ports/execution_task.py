"""Single-execution source and actual rights; the common task loop stays shared."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from .lifecycle import OperationControl
from lab_generate_skill.domain.lifecycle import OperationContext
from .task_execution import TaskClosureAuthority


class ExecutionTaskSources(Protocol):
    def load(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ExecutionSourceFacts: ...


class ExecutionTaskAuthority(TaskClosureAuthority, Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        """Actual source/claim/writer/resources, not approval by a descriptor."""
        ...

    def verify_initial(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        facts: CandidateFacts,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> None:
        """Actual original exclusive browser/model/source and full initial facts."""
        ...


class ExecutionTaskSourceChecks(Protocol):
    """Full immutable evidence proof; never the durable claim/permission check."""

    def load_source(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ExecutionSourceFacts: ...


@runtime_checkable
class ExecutionTaskSourceRechecks(Protocol):
    """Recheck live rights for facts handed through this same admission only."""

    def recheck(
        self,
        plan: TaskExecutionPlan,
        facts: ExecutionSourceFacts,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...


@runtime_checkable
class ExecutionTaskSourceCurrentChecks(Protocol):
    def verify_current(
        self,
        plan: TaskExecutionPlan,
        facts: ExecutionSourceFacts,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
