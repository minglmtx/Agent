"""Claimed category member on original model and sole owned lifecycle."""

from dataclasses import dataclass
from pathlib import Path
from contextlib import ExitStack
from lab_generate_skill.application.execution_stage import execution_stage
import time
from typing import Any
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_resource_records import check_operation
from lab_generate_skill.adapters.plans.closed_actor_inputs import (
    SupervisedActorAcquisitionReads,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.sites.task_preparation_inputs import (
    TaskPreparationDeclarationInputs,
)
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.ports.lifecycle import Clock, OperationControls, ResourceJournal
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from .claimed_actor_resource import claimed_actor_resource
from .shopping_category_production_admission import ClaimedCategoryNavigationMember
from .shopping_category_production_execution import (
    category_site_acquisition_context,
    bind_category_production_execution,
)
from .shopping_category_production_site import DeclaredCategoryNavigationSite
from .shopping_category_source_publication import PublishedCategoryNavigationSource
from .shopping_category_review_material import completed_category_review_material
from .shopping_category_owned_execution import OwnedCategoryNavigationExecution
from .task_actor import CurrentTaskActorBinding, TaskActorResources


@dataclass(frozen=True)
class CategoryNavigationMemberCompletion:
    result: ExecutionTaskResult
    review_material: dict[str, Any]
    phase_seconds: dict[str, float]
    preparation_stages: tuple[tuple[str, str, float], ...]
    input_reuse: dict[str, dict[str, int] | None] | None = None


def member_input_reuse(
    owned: OwnedCategoryNavigationExecution | None,
) -> dict[str, dict[str, int] | None]:
    """Copy actual one-shot consumer counters; never permission or resume state."""
    if owned is None:
        return {}
    declaration = owned.bundle.preparation.declared_inputs
    inputs = owned.resources.inputs
    return {
        "preparation_declaration_reuse": (
            dict(declaration.statistics)
            if isinstance(declaration, TaskPreparationDeclarationInputs)
            else None
        ),
        "trace_event_reuse": (
            None if inputs is None else dict(inputs.trace_input_statistics)
        ),
    }


def execute_claimed_category_member(
    member: ClaimedCategoryNavigationMember,
    source: PublishedCategoryNavigationSource,
    candidate: DeclaredCategoryNavigationSite,
    model: ActorResourceSpec,
    model_operation: OperationContext,
    template: BrowserWorkerConfiguration,
    actor: TaskActorInitialization,
    *,
    journal: ResourceJournal,
    controls: OperationControls,
    clock: Clock,
    allocation_verifier: SlurmAllocationVerifier,
    output: Path,
    workspace_root: Path,
    site_seconds: int,
    task_seconds: int,
    source_reads: ClosedSourceReadTransport,
) -> CategoryNavigationMemberCompletion:
    if (
        not isinstance(member, ClaimedCategoryNavigationMember)
        or not isinstance(source, PublishedCategoryNavigationSource)
        or not isinstance(candidate, DeclaredCategoryNavigationSite)
        or not isinstance(source_reads, ClosedSourceReadTransport)
    ):
        raise TypeError(
            "Original category claimed member/source/deferred site/reader required"
        )
    model = ActorResourceSpec.model_validate(model)
    model_operation = OperationContext.model_validate(model_operation)
    template = BrowserWorkerConfiguration.model_validate(template)
    actor = TaskActorInitialization.model_validate(actor)
    check_operation(model, model_operation, "execute")
    d, owner = member.declarations, member.owner
    if (
        candidate.deferred_acquisition is not True
        or candidate.spec.token.owner != owner.run.owner
        or candidate.spec.configuration.site_id != "shopping"
        or source.material.context_ref
        != member.admitted.published.source.source_context_receipt_ref
        or source.receipt.scope.owner != owner.run.owner
        or candidate.public.identity != d.plan.intent.binding.task
        or model.token != actor.model_allocation
        or model.token.owner != owner.run.owner
        or model.release_ref != owner.run.release_ref
        or template.installation != candidate.spec.configuration.installation
        or template.installation.manifest_ref != model.release_ref
        or source_reads.store is not owner.evidence
    ):
        raise OwnershipConflict(
            "Category member changed source/owner/model/site/release"
        )
    if (
        type(site_seconds) is not int
        or not 1 <= site_seconds <= 7200
        or type(task_seconds) is not int
        or not 1 <= task_seconds <= 14400
        or not isinstance(controls, BoundedOperationControls)
    ):
        raise ValueError(
            "Original bounded category acquisition/task controller required"
        )
    if (
        not isinstance(output, Path)
        or output.resolve(strict=True) != output
        or not output.is_dir()
        or not isinstance(workspace_root, Path)
    ):
        raise ValueError("Original provisioned output/workspace required")
    controls.bind(model_operation).checkpoint()
    resources: list[TaskActorResources] = []
    seconds: dict[str, float] = {}
    owned = None
    result = None
    start = time.monotonic()
    try:
        with ExitStack() as model_stack:
            with execution_stage(controls, "model", model_operation):
                engine = model_stack.enter_context(
                    claimed_actor_resource(
                        owner,
                        model,
                        model_operation,
                        journal=journal,
                        controls=controls,
                        clock=clock,
                        workspace_root=workspace_root,
                        allocation_verifier=allocation_verifier,
                    )
                )
            seconds["model_acquisition"] = time.monotonic() - start
            model_scope = ActorExecutionScope(
                model,
                journal,
                owner.evidence,
                engine,
                model_operation,
                controls.bind(model_operation),
                cleanup_seconds=actor.cleanup_seconds,
                acquisition_reads=SupervisedActorAcquisitionReads(
                    source.material, source_reads
                ),
            )
            acquisition = category_site_acquisition_context(
                candidate.spec, candidate.acquisition, d, clock, seconds=site_seconds
            )
            controls.narrow_execution(model_operation, seconds=task_seconds)
            owned = bind_category_production_execution(
                d,
                owner,
                member.admitted.reader,
                model_scope,
                candidate.spec,
                acquisition,
                template,
                actor,
                journal=journal,
                bindings=member.admitted.bindings,
                controls=controls,
                clock=clock,
                trace_root=output / "trace",
                calls_root=output / "calls",
                trace_capacity=TraceCapacity(
                    max_events=128,
                    max_bytes=2 * 1024**2,
                    max_event_bytes=32768,
                    max_trace_bytes=2 * 1024**2,
                ),
            )
            actors = owned.bundle.task.deps.actors
            if not isinstance(actors, CurrentTaskActorBinding):
                raise TypeError("Original concrete category Actor binding required")
            factory = actors.resources

            def retain(
                initialized: InitializedTask, prepared: PreparedActorInput
            ) -> TaskActorResources:
                resource = factory(initialized, prepared)
                resources.append(resource)
                return resource

            actors.resources = retain
            start = time.monotonic()
            result = owned.bundle.task.execute(d.plan.intent, d.plan.operation)
            seconds["task_lifecycle"] = time.monotonic() - start
            if len(resources) != 1:
                raise ValueError(
                    "One original category Actor resource binding required"
                )
            snapshot = resources[0].journal.read(
                d.plan.read_operation.cleanup(
                    "category.actor.trace-review-read",
                    now=clock.utcnow(),
                    seconds=d.plan.cleanup_seconds,
                )
            )
            executions = tuple(resources[0].completed)
            start = time.monotonic()
        seconds["model_close"] = time.monotonic() - start
        record = journal.read(
            model.token,
            model_operation.cleanup(
                "category.actor.closed-review",
                now=clock.utcnow(),
                seconds=d.plan.cleanup_seconds,
            ),
        )
        material = completed_category_review_material(
            owned,
            source.material,
            result,
            record,
            snapshot,
            executions,
            output / "evidence",
        )
        return CategoryNavigationMemberCompletion(
            result,
            material,
            seconds,
            tuple(owned.bundle.preparation.state.stage_timings),
            member_input_reuse(owned),
        )
    except BaseException as error:
        setattr(error, "category_original_member", member)
        setattr(error, "category_owned_execution", owned)
        setattr(error, "category_task_result", result)
        setattr(error, "category_phase_seconds", dict(seconds))
        setattr(error, "category_input_reuse", member_input_reuse(owned))
        setattr(
            error,
            "category_model_executions",
            tuple(x for resource in resources for x in resource.completed),
        )
        raise
