"""Bind preparation admission to original current journals and physical authority."""

from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
)
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_preparation_inputs import (
    PreparationDeclarationInputs,
)
from .context_evidence import read_bytes
from .task_state_admission import TaskStateAdmission


class TaskPreparationAuthority:
    def __init__(
        self,
        sources: TaskPhaseSources,
        runs: RunJournal,
        authority: TaskPhaseResourceAuthority,
        evidence: EvidenceStore,
    ) -> None:
        if any(value is None for value in (sources, runs, authority, evidence)):
            raise ValueError(
                "Original journals and physical/source authority are mandatory"
            )
        self.sources, self.runs, self.authority, self.evidence = (
            sources,
            runs,
            authority,
            evidence,
        )
        self.current = TaskStateAdmission(sources, runs, authority, evidence)
        self.preparation_inputs: PreparationDeclarationInputs | None = None

    def use_preparation_inputs(self, inputs: PreparationDeclarationInputs) -> None:
        if self.preparation_inputs is not None:
            raise OwnershipConflict("Preparation declaration input binding is one-shot")
        self.preparation_inputs = inputs

    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        plan = TaskExecutionPlan.model_validate(plan)
        declaration = SiteTaskPreparationPlan.model_validate(declaration)
        operation = OperationContext.model_validate(operation)
        known = (
            None
            if self.preparation_inputs is None
            else self.preparation_inputs.require(plan, declaration, operation, control)
        )

        def proof(
            progress: TaskPhaseSourceState, snapshot: RunSnapshot, reset: ResetPlan
        ) -> None:
            if (
                plan.declaration_ref.content_schema != declaration.schema_version
                or (
                    read_bytes(
                        self.evidence, plan.declaration_ref, 2 * 1024**2, control
                    )
                    if known is None
                    else known.declaration.model_dump_json().encode()
                )
                != declaration.model_dump_json().encode()
            ):
                raise OwnershipConflict(
                    "Preparation declaration differs from original frozen bytes"
                )
            binding = (
                known.binding
                if known is not None
                else TaskBinding.model_validate_json(
                    read_bytes(
                        self.evidence,
                        declaration.task_binding_ref,
                        2 * 1024**2,
                        control,
                    )
                )
            )
            scope = declaration.scope
            if (
                binding != progress.task
                or (scope.owner, scope.task, scope.attempt_id)
                != (
                    plan.intent.binding.run.owner,
                    plan.intent.binding.task,
                    plan.intent.binding.attempt_id,
                )
                or reset.scope != scope
            ):
                raise OwnershipConflict(
                    "Preparation changed original task/reset binding"
                )

        self.current.verify(
            plan,
            declaration.scope,
            operation,
            control,
            stages=("acquiring", "preparing"),
            cleanup_parents=(
                declaration.prepare_operation.operation_id,
                declaration.environment_operation.operation_id,
            ),
            proof=proof,
            reset_input=None if known is None else known.reset,
        )
