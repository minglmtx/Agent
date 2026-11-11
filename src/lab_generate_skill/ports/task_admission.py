"""One task admission interface for the shared lifecycle; no default permission."""

from typing import Protocol
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from .lifecycle import OperationControl
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution_result import TaskFailureContext


class TaskLifecycleAdmission(Protocol):
    def failure_context(
        self,
        plan: TaskExecutionPlan,
        failure_type: str,
        references: tuple[EvidenceRef, ...],
    ) -> TaskFailureContext: ...

    def open(
        self, plan: TaskExecutionPlan, snapshot: RunSnapshot, control: OperationControl
    ) -> TaskAdmissionState: ...
    def verify_current(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        operation: OperationContext,
    ) -> None: ...
    def verify_resources(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None: ...
    def initialize(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        initialized: InitializedTask,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> PreparedActorInput: ...
