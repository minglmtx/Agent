"""Current executing attempt/Actor output grant for terminal collection."""

from collections.abc import Callable
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import BrowserAcquiredFact
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.trace_journal import TraceJournal
from .context_evidence import read_bytes
from .task_state_admission import TaskStateAdmission


class TaskCaptureAuthority:
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        sources: TaskPhaseSources,
        runs: RunJournal,
        authority: TaskPhaseResourceAuthority,
        trace: Callable[[], TraceJournal],
        evidence: EvidenceStore,
    ) -> None:
        if (
            declaration_ref.content_schema
            not in ("task-capture-plan/1", "task-capture-plan/2")
            or (declaration_ref.visibility, declaration_ref.media_type)
            != ("private", "application/json")
            or trace is None
        ):
            raise ValueError(
                "Original frozen capture declaration and TraceJournal required"
            )
        self.declaration_ref, self.evidence, self.trace = (
            declaration_ref,
            evidence,
            trace,
        )
        self.current = TaskStateAdmission(sources, runs, authority, evidence)

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskCapturePlan,
        inputs: TaskCaptureInputs,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        declaration = TaskCapturePlan.model_validate(declaration)
        if self.declaration_ref.content_schema != declaration.schema_version:
            raise OwnershipConflict(
                "Capture declaration changed original schema version"
            )
        acquired = BrowserAcquiredFact.model_validate_json(
            read_bytes(
                self.evidence,
                inputs.initial.browser_acquired_ref,
                64 * 1024**2,
                control,
            )
        )
        parent = acquired.operation.parent_operation_id
        if parent is None:
            raise OwnershipConflict("Original browser acquisition parent required")

        def proof(
            progress: TaskPhaseSourceState, current: RunSnapshot, reset: ResetPlan
        ) -> None:
            if (
                read_bytes(self.evidence, self.declaration_ref, 2 * 1024**2, control)
                != declaration.model_dump_json().encode()
            ):
                raise OwnershipConflict("Original frozen capture declaration changed")
            binding = TaskBinding.model_validate_json(
                read_bytes(
                    self.evidence,
                    plan.evaluation.task_contract_ref,
                    2 * 1024**2,
                    control,
                )
            )
            attempt = next(
                a for a in current.project()[1] if a.binding == plan.intent.binding
            )
            original = next((e for e in attempt.events if e.stage == "executing"), None)
            baseline = next(
                (e for e in attempt.events if e.stage == "baseline_verified"), None
            )
            if original is None or len(original.outputs) != 2 or baseline is None:
                raise OwnershipConflict(
                    "Original admitted Actor/baseline outputs required"
                )
            actor = ActorRunRequest.model_validate_json(
                read_bytes(self.evidence, original.outputs[1], 2 * 1024**2, control)
            )
            read = operation.model_copy(
                update={"operation_id": operation.operation_id + ".capture-proof-trace"}
            )
            if (
                binding != progress.task
                or reset.scope != declaration.scope
                or actor != inputs.initialized.actor
                or (inputs.initialized.baseline_ref, inputs.initialized.equivalence_ref)
                != baseline.outputs
                or acquired.token != actor.browser_allocation
                or snapshot.plan.binding != plan.intent.binding
                or snapshot.plan.scope != declaration.scope
                or self.trace().read(read) != snapshot
            ):
                raise OwnershipConflict(
                    "Capture changed original task/Actor/baseline/trace"
                )

        self.current.verify(
            plan,
            declaration.scope,
            operation,
            control,
            stages=("executing",),
            cleanup_parents=(parent,),
            proof=proof,
        )
