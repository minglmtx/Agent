"""Original construction admission behind the shared task lifecycle interface.

Keep the full pending-intent, claim, stable journals and measured candidate
checks here. This adapter stores a comparison snapshot, never a reusable grant;
every live gate rereads original histories and source claims.
"""

from typing import Protocol
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .initialize_task import initialize_task
from .construction_actor_configuration import verify_construction_actor_configuration

from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from .admit_candidate import CandidateAdmissionDeps


class ConstructionAdmissionInputs(Protocol):
    @property
    def construction(self) -> ConstructionJournal: ...
    @property
    def runs(self) -> RunJournal: ...
    @property
    def admission(self) -> CandidateAdmissionDeps: ...
    @property
    def authority(self) -> TaskExecutionAuthority: ...
    @property
    def evidence(self) -> EvidenceStore: ...
    @property
    def controls(self) -> OperationControls: ...


from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.domain.evidence import EvidenceRef


class ConstructionTaskAdmission:
    def failure_context(
        self,
        plan: TaskExecutionPlan,
        failure_type: str,
        references: tuple[EvidenceRef, ...],
    ) -> TaskFailureContext:
        return TaskFailureContext(
            schema_version="task-failure-context/1",
            intent=plan.intent,
            failure_type=failure_type,
            references=references,
        )

    def __init__(self, deps: ConstructionAdmissionInputs) -> None:
        self.deps = deps
        self.original: ConstructionProgress | None = None
        self.state: TaskAdmissionState | None = None

    def _original(
        self, plan: TaskExecutionPlan, state: TaskAdmissionState
    ) -> ConstructionProgress:
        if (
            self.original is None
            or self.state != state
            or state.source_kind != "construction"
            or state.binding != plan.intent.binding
        ):
            raise OwnershipConflict("Original task admission view changed")
        return self.original

    def open(
        self, plan: TaskExecutionPlan, snapshot: RunSnapshot, control: OperationControl
    ) -> TaskAdmissionState:
        control.checkpoint()
        if plan.intent.source_kind != "construction":
            raise OwnershipConflict(
                "Construction admission cannot consume execution-only plans"
            )
        original = ConstructionProgress.model_validate(
            self.deps.construction.read(plan.read_operation)
        )
        if self.original is not None and self.original != original:
            raise RevisionConflict(
                "Original task source changed; no rebind to another attempt"
            )
        self.original = original
        self.state = TaskAdmissionState(
            source_kind="construction",
            binding=plan.intent.binding,
            max_generations=original.plan.max_actor_generations,
            max_interactions=original.plan.max_interactions,
        )
        return self.state

    def verify_current(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        operation: OperationContext,
    ) -> None:
        deps, progress = self.deps, self._original(plan, state)
        control = deps.controls.bind(operation)
        control.checkpoint()
        run, _ = snapshot.project()
        if (
            snapshot.binding != plan.intent.binding.run
            or run.stage != "running"
            or run.stop_reason is not None
        ):
            raise InvalidTransition(
                "New task work requires original running unstopped run"
            )
        if (
            progress.plan.run != snapshot.binding
            or progress.project().pending_attempt != plan.intent
        ):
            raise OwnershipConflict(
                "Task must be the exact original pending construction attempt"
            )
        claim = deps.admission.claims.require(
            progress.plan.claim_ref, plan.intent.binding, operation
        )
        check_source_claim(
            claim, progress.plan.claim_ref, progress.plan.run, progress.plan.task
        )
        if (
            deps.runs.read(plan.read_operation) != snapshot
            or deps.construction.read(plan.read_operation) != progress
        ):
            raise RevisionConflict(
                "Original task journals changed during execution admission"
            )
        control.checkpoint()

    def verify_resources(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        self.deps.authority.verify(
            plan, self._original(plan, state), snapshot, reset, control
        )

    def initialize(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        initialized: InitializedTask,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> PreparedActorInput:
        deps, progress = self.deps, self._original(plan, state)
        if (
            deps.admission.runs.read(plan.read_operation) != snapshot
            or deps.admission.construction.read(plan.read_operation) != progress
        ):
            raise OwnershipConflict(
                "Candidate admission must use the actual original journals"
            )
        verify_construction_actor_configuration(
            progress.plan, initialized.actor, deps.evidence, control
        )
        admitted = initialize_task(
            plan, initialized, deps.admission, deps.evidence, control
        )
        if (
            admitted.run_revision != snapshot.revision
            or admitted.construction_revision != progress.revision
        ):
            raise RevisionConflict("Actor admission changed original task revisions")
        return admitted
