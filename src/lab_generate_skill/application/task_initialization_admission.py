"""Starting-phase/source grant for the original current initialization producer."""

from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPrepared,
    SiteTaskPreparationPlan,
)
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
)
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_state_admission import TaskStateAdmission
from .context_evidence import read_bytes


class TaskInitializationAuthority:
    def __init__(
        self,
        declaration_ref: EvidenceRef,
        sources: TaskPhaseSources,
        runs: RunJournal,
        authority: TaskPhaseResourceAuthority,
        evidence: EvidenceStore,
    ) -> None:
        if (declaration_ref.content_schema, declaration_ref.visibility) != (
            "task-initialization-plan/2",
            "private",
        ):
            raise ValueError(
                "Original frozen private initialization declaration required"
            )
        self.declaration_ref, self.evidence = declaration_ref, evidence
        self.current = TaskStateAdmission(sources, runs, authority, evidence)

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._verify(plan, declaration, operation, control, None)

    def verify_with_inputs(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        inputs: InitializationAdmissionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if not isinstance(inputs, InitializationAdmissionInputs):
            raise TypeError("Exact same-call initialization inputs required")
        inputs.require_original(plan, self.declaration_ref, declaration)
        self._verify(plan, declaration, operation, control, inputs)

    def _verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskInitializationPlan,
        operation: OperationContext,
        control: OperationControl,
        inputs: InitializationAdmissionInputs | None,
    ) -> None:
        declaration = TaskInitializationPlan.model_validate(declaration)

        def proof(
            progress: TaskPhaseSourceState, snapshot: RunSnapshot, reset: ResetPlan
        ) -> None:
            if inputs is None and (
                read_bytes(self.evidence, self.declaration_ref, 2 * 1024**2, control)
                != declaration.model_dump_json().encode()
            ):
                raise OwnershipConflict(
                    "Initialization differs from original frozen declaration"
                )
            prepared = (
                inputs.prepared
                if inputs is not None
                else SiteTaskPrepared.model_validate_json(
                    read_bytes(
                        self.evidence,
                        declaration.prepared_result_ref,
                        2 * 1024**2,
                        control,
                    )
                )
            )
            prepared_plan = (
                inputs.preparation
                if inputs is not None
                else SiteTaskPreparationPlan.model_validate_json(
                    read_bytes(
                        self.evidence, plan.declaration_ref, 2 * 1024**2, control
                    )
                )
            )
            binding = (
                inputs.binding
                if inputs is not None
                else TaskBinding.model_validate_json(
                    read_bytes(
                        self.evidence,
                        prepared_plan.task_binding_ref,
                        2 * 1024**2,
                        control,
                    )
                )
            )
            original = next(
                a for a in snapshot.project()[1] if a.binding == plan.intent.binding
            )
            acquired = (
                inputs.acquired
                if inputs is not None
                else SiteTaskAcquired.model_validate_json(
                    read_bytes(
                        self.evidence, prepared.acquired_ref, 2 * 1024**2, control
                    )
                )
            )
            acquiring = next(
                (e for e in original.events if e.stage == "acquiring"), None
            )
            preparing = next(
                (e for e in original.events if e.stage == "preparing"), None
            )
            if (
                prepared.declaration_ref != plan.declaration_ref
                or binding != progress.task
                or declaration.prepared_result_ref not in original.events[-1].outputs
                or reset.scope != declaration.scope
                or prepared.scope != declaration.scope
                or declaration.source_context_receipt_ref
                != progress.context_receipt_ref
                or plan.intent.public_context_ref != progress.public_context_ref
                or acquired.declaration_ref != plan.declaration_ref
                or acquired.scope != declaration.scope
                or acquiring is None
                or acquired.operation != acquiring.operation
                or preparing is None
                or prepared.acquired_ref not in preparing.outputs
            ):
                raise OwnershipConflict(
                    "Initialization changed original starting output/task/reset"
                )

        self.current.verify(
            plan,
            declaration.scope,
            operation,
            control,
            stages=("starting",),
            cleanup_parents=(
                declaration.browser_acquisition.operation_id,
                declaration.capture_operation.operation_id,
                declaration.initial_operation.operation_id,
                declaration.baseline_operation.operation_id,
                declaration.comparison_operation.operation_id,
                declaration.equivalence_operation.operation_id,
            ),
            proof=proof,
            reset_input=None if inputs is None else inputs.reset,
        )
