"""Late original acquisition and concrete category browser binding; no effects."""

from datetime import timedelta
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.ports.lifecycle import Clock, OperationControls, ResourceJournal
from lab_generate_skill.ports.task_bindings import TaskBindings
from .shopping_category_browser_declarations import (
    OriginalShoppingCategoryBrowserDeclarations,
)
from .shopping_category_owned_execution import (
    shopping_category_owned_execution,
    OwnedCategoryNavigationExecution,
)
from .task_execution_bindings import TaskExecutionDeclarations


def category_site_acquisition_context(
    site: SiteResourceSpec,
    parent: OperationContext,
    declarations: TaskExecutionDeclarations,
    clock: Clock,
    *,
    seconds: int,
) -> OperationContext:
    site = SiteResourceSpec.model_validate(site)
    parent = OperationContext.model_validate(parent)
    if not isinstance(declarations, TaskExecutionDeclarations):
        raise TypeError("Original category declarations required")
    if type(seconds) is not int or not 1 <= seconds <= 7200:
        raise ValueError("Bounded original category acquisition required")
    inputs = site.configuration.shopping_category_inputs
    scope = declarations.reset.scope
    plan = declarations.plan
    if (
        inputs is None
        or inputs.scope != scope
        or site.configuration.schema_version != "site-worker-configuration/9"
        or plan.intent.binding.task != scope.task
        or plan.intent.binding.attempt_id != scope.attempt_id
        or plan.intent.binding.run.owner != scope.owner
        or (
            parent.run_id,
            parent.owner_id,
            parent.mode,
            parent.operation_id,
            parent.allocation_id,
            parent.recovery_ref,
        )
        != (
            scope.owner.run_id,
            scope.owner.owner_id,
            "execute",
            site.token.allocation_id + ".acquire",
            site.token.allocation_id,
            site.token.recovery_ref,
        )
        or declarations.preparation.resource_read_operation.parent_operation_id
        != parent.operation_id
    ):
        raise OwnershipConflict(
            "Category acquisition changed original task/resource lineage"
        )
    operation = parent.model_copy(
        update={
            "deadline": min(
                parent.deadline,
                plan.operation.deadline,
                clock.utcnow() + timedelta(seconds=seconds),
            )
        }
    )
    site.check_operation(operation, "execute")
    return operation


def bind_category_production_execution(
    declarations: TaskExecutionDeclarations,
    owner: ClaimedRunResourceOwner,
    source: OriginalExecutionTaskSource,
    model: ActorExecutionScope,
    site: SiteResourceSpec,
    acquisition: OperationContext,
    template: BrowserWorkerConfiguration,
    actor: TaskActorInitialization,
    *,
    journal: ResourceJournal,
    bindings: TaskBindings,
    controls: OperationControls,
    clock: Clock,
    trace_root: Path,
    calls_root: Path,
    trace_capacity: TraceCapacity,
) -> OwnedCategoryNavigationExecution:
    site = SiteResourceSpec.model_validate(site)
    acquisition = OperationContext.model_validate(acquisition)
    template = BrowserWorkerConfiguration.model_validate(template)
    actor = TaskActorInitialization.model_validate(actor)
    site.check_operation(acquisition, "execute")
    if (
        site.configuration.site_id != "shopping"
        or site.configuration.shopping_category_inputs is None
        or site.configuration.installation != template.installation
        or model.binding.release_ref != template.installation.manifest_ref
        or model.binding.resource != actor.model_allocation
        or declarations.plan != owner.task_plan
        or site.token.owner != owner.run.owner
    ):
        raise OwnershipConflict(
            "Category final binding changed model/task/site/installation"
        )
    controls.bind(acquisition).checkpoint()
    browser = OriginalShoppingCategoryBrowserDeclarations(
        owner, model, declarations.reset, template, actor
    )
    return shopping_category_owned_execution(
        declarations,
        owner,
        source,
        model,
        site,
        acquisition,
        browser,
        journal=journal,
        bindings=bindings,
        controls=controls,
        clock=clock,
        trace_root=trace_root,
        calls_root=calls_root,
        trace_capacity=trace_capacity,
    )
