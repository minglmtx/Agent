"""Pure exact original source/preparation/browser/Actor initialization binding."""

from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPrepared,
    SiteTaskPreparationPlan,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_initialization import PublicNavigation
from lab_generate_skill.domain.preparation import PreparedTask, EnvironmentBaseline
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.site_task import SiteTaskRequest
from .evidence_bytes import require_complete_bytes


def require_original_initialization(
    plan: TaskExecutionPlan,
    declaration: TaskInitializationPlan,
    original: SiteTaskPrepared,
    prepared_plan: SiteTaskPreparationPlan,
    prepared: PreparedTask,
    environment: EnvironmentBaseline,
    source: PublicContextReceipt,
    source_inputs: PublicContextInputs,
    reset: ResetPlan,
    browser: BrowserResourceSpec,
    acquired: SiteTaskAcquired,
    request: SiteTaskRequest,
    *,
    adoption: InitialAdoptionInputs | None = None,
) -> None:
    scope, binding = declaration.scope, plan.intent.binding
    if (scope.owner, scope.task, scope.attempt_id) != (
        binding.run.owner,
        binding.task,
        binding.attempt_id,
    ) or any(
        s != scope
        for s in (
            original.scope,
            prepared_plan.scope,
            prepared.scope,
            reset.scope,
            environment.scope,
        )
    ):
        raise OwnershipConflict("Initialization changed original pending attempt scope")
    if (
        original.declaration_ref != plan.declaration_ref
        or prepared.task_binding_ref != prepared_plan.task_binding_ref
        or prepared.task_binding_ref != plan.evaluation.task_contract_ref
        or prepared.private_checks_ref != plan.evaluation.completion_spec_ref
        or original.publication.selection.environment_ref != original.environment_ref
        or prepared.spec_ref != reset.spec_ref
    ):
        raise OwnershipConflict(
            "Initialization changed original prepared task/baseline contract"
        )
    if (
        request.action != "prepare"
        or request.task != scope.task
        or request.binding_ref != prepared.task_binding_ref
    ):
        raise OwnershipConflict(
            "Initialization changed original native preparation request"
        )
    # Native input may wrap the bound private completion spec. Keep that frozen
    # wire input exact, and keep the task/private/evaluation joins above exact;
    # their references need not be the same object or schema.
    require_complete_bytes(
        prepared_plan.private_input_ref, request.private_input.encode()
    )
    if adoption is not None:
        adoption = InitialAdoptionInputs.model_validate(adoption)
        if (
            adoption.binding.binding != binding
            or adoption.binding.scope != scope
            or adoption.binding.execution_source_ref != plan.source_ref
            or adoption.source.intent != plan.intent
        ):
            raise OwnershipConflict(
                "Initialization changed the selected current adoption"
            )
        adoption.require_source(
            declaration.source_context_receipt_ref, source, source_inputs
        )
    if (
        (adoption is None and source.scope.owner != scope.owner)
        or source.scope.task != scope.task
        or source.scope.attempt_id == scope.attempt_id
        or source.public_context_ref != plan.intent.public_context_ref
        or source_inputs.context.task != prepared.public_task
        or source.spec_ref != prepared.spec_ref
    ):
        raise OwnershipConflict(
            "Original qualified source/public task and distinct candidate attempt required"
        )
    tokens = tuple(
        token for token in reset.attempt_allocations if token.resource_kind == "browser"
    )
    if (
        len(tokens) != 1
        or tokens[0] != browser.token
        or browser.configuration.spec.scope != scope
        or browser.configuration.spec.task != prepared.public_task
    ):
        raise OwnershipConflict(
            "Initialization changed original declared browser allocation"
        )
    selected = browser.configuration.initialization
    if isinstance(selected, PublicNavigation):
        raise OwnershipConflict("Original prepared task initialization is mandatory")
    if (
        selected.prepared_ref != original.publication.prepared_ref
        or selected.site_ref != acquired.site_started_ref
        or acquired.scope != scope
        or acquired.declaration_ref != original.declaration_ref
        or acquired.operation
        != plan.operation.model_copy(
            update={"operation_id": plan.operation.operation_id + ".acquiring"}
        )
    ):
        raise OwnershipConflict(
            "Initialization changed original complete preparation/site reference"
        )
    selected.check(browser.configuration.spec)
    browser.check_operation(declaration.browser_acquisition, "execute")
    browser.check_operation(declaration.capture_operation, "execute")
    operations = (
        declaration.browser_acquisition,
        declaration.capture_operation,
        declaration.initial_operation,
        declaration.baseline_operation,
        declaration.comparison_operation,
        declaration.equivalence_operation,
    )
    if any(
        op.deadline > plan.operation.deadline
        or op.cancellation_ref != plan.operation.cancellation_ref
        for op in operations
    ):
        raise OwnershipConflict(
            "Initialization widened original deadline/cancellation scope"
        )
    if declaration.actor.revision_round != (
        0 if plan.intent.candidate_slot < 4 else plan.intent.candidate_slot - 3
    ):
        raise OwnershipConflict(
            "Actor revision differs from original construction candidate slot"
        )
