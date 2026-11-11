"""Explicit current adoption in the existing owned initializer; no new lifecycle."""

from lab_generate_skill.adapters.ledger.stage_execution_authority import (
    StageExecutionClaimAuthority,
)
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.initial_adoption import (
    ExecutionInitialAdoptionAuthority,
)
from lab_generate_skill.adapters.plans.stage_validation_source import (
    SupervisedStageValidationSourceChecks,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_adoption import (
    InitialAdoptionBinding,
    InitialAdoptionInputs,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControls


def stage_initial_adoption_checks(
    plan: TaskExecutionPlan,
    scope: StateScope,
    source: OriginalExecutionTaskSource,
    operation: OperationContext,
    controls: OperationControls,
) -> ExecutionInitialAdoptionAuthority | None:
    plan = TaskExecutionPlan.model_validate(plan)
    if not isinstance(source, OriginalExecutionTaskSource) or controls is None:
        raise TypeError("Actual original source reader and operation controls required")
    if plan.source_ref is None:
        raise OwnershipConflict("An execution source is required")
    if plan.source_ref.content_schema == "execution-task-source/1":
        return None  # Ordinary tasks retain the existing continuous initialization.
    if (
        plan.source_ref.content_schema != "execution-task-source/2"
        or not isinstance(source.claims, FileSourceStageValidations)
        or not isinstance(source.source_checks, SupervisedStageValidationSourceChecks)
        or not isinstance(source.source_checks.owner, StageExecutionClaimAuthority)
        or not isinstance(source.contexts, ClosedSourceContexts)
        or source.source_checks.contexts is not source.contexts._records
        or source.source_checks.owner.contexts is not source.contexts
    ):
        raise TypeError(
            "Actual stage-admitted source/claim/owner required for adoption"
        )
    read = operation.model_copy(
        update={
            "operation_id": operation.operation_id + ".initial-selection",
            "attempt_id": None,
            "allocation_id": None,
            "recovery_ref": None,
        }
    )
    facts = source.load(plan, read, controls.bind(read))
    if (
        facts.source.frozen_origin is None
        or facts.source.frozen_origin.validation != source.claims.validation
        or facts.source.frozen_origin != source.source_checks.owner.origin
    ):
        raise OwnershipConflict("Adoption changed its actual stage admission")
    inputs = InitialAdoptionInputs(
        binding=InitialAdoptionBinding(
            scope=scope,
            binding=plan.intent.binding,
            execution_source_ref=plan.source_ref,
            source_context_ref=facts.source.source_context_receipt_ref,
        ),
        source=facts.source,
    )
    live = ExecutionInitialAdoptionAuthority(plan, inputs, source)
    live.verify_adoption(inputs, operation, controls.bind(operation))
    return live
