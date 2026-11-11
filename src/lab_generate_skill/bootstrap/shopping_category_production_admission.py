"""Current category claim/run registration and phase binding; no resource effects."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import (
    RunEvent,
    RunStage,
    SubmissionObservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.run_journal import RunEntry
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from .execution_source_admission import AdmittedExecutionSource
from .shopping_category_execution_admission import (
    admit_shopping_category_execution_source,
)
from .shopping_category_execution_configuration import (
    prepare_category_execution_configuration,
)
from .shopping_category_run_configuration import FrozenCategoryNavigationRun
from .shopping_category_source_publication import PublishedCategoryNavigationSource
from .task_execution_bindings import TaskExecutionDeclarations


@dataclass(frozen=True)
class ClaimedCategoryNavigationMember:
    admitted: AdmittedExecutionSource
    declarations: TaskExecutionDeclarations
    owner: ClaimedRunResourceOwner


def admit_category_production_member(
    source: PublishedCategoryNavigationSource,
    frozen: FrozenCategoryNavigationRun,
    private: CategoryNavigationSpec,
    scope: StateScope,
    site: SiteResourceSpec,
    acquisition: OperationContext,
    environment: RecoveryPlan,
    execution: SlurmExecutionIdentity,
    controller: SlurmCgroupMembership,
    operation: OperationContext,
    *,
    run_root: Path,
    claim_root: Path,
    claim_scope: str,
    accounting_ref: EvidenceRef,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
    source_reads: ClosedSourceReadTransport,
    physical_close_seconds: int,
) -> ClaimedCategoryNavigationMember:
    if (
        not isinstance(source, PublishedCategoryNavigationSource)
        or not isinstance(frozen, FrozenCategoryNavigationRun)
        or not isinstance(source_reads, ClosedSourceReadTransport)
    ):
        raise TypeError(
            "Actual category source, frozen run and controlled reader required"
        )
    scope = StateScope.model_validate(scope)
    execution = SlurmExecutionIdentity.model_validate(execution)
    controller = SlurmCgroupMembership.model_validate(controller)
    operation = OperationContext.model_validate(operation)
    frozen.run.check_binding(frozen.binding)
    if (
        frozen.binding.owner != scope.owner
        or scope.owner.job_id != execution.job_id
        or frozen.inputs.source_context_receipt_ref != source.material.context_ref
        or frozen.inputs.attempt_id != scope.attempt_id
        or frozen.task.identity != scope.task
        or source.receipt.scope.owner != scope.owner
        or source.material.site.slurm.execution != execution
        or source.material.site.slurm.parent != controller
        or source_reads.store is not evidence
        or (operation.run_id, operation.owner_id, operation.attempt_id, operation.mode)
        != (scope.owner.run_id, scope.owner.owner_id, None, "execute")
        or accounting_ref.content_schema != "original-slurm-accounting/1"
        or accounting_ref.visibility != "private"
    ):
        raise OwnershipConflict(
            "Category admission changed original source/run/controller/store"
        )
    if (
        not isinstance(run_root, Path)
        or run_root.resolve(strict=True) != run_root
        or not run_root.is_dir()
    ):
        raise ValueError("Original preprovisioned canonical category run root required")
    admitted = None
    try:
        admitted = admit_shopping_category_execution_source(
            frozen.run,
            frozen.binding,
            source.material,
            execution,
            controller,
            operation,
            claim_root=claim_root,
            claim_scope=claim_scope,
            evidence=evidence,
            controls=controls,
            source_reads=source_reads,
        )
        declarations = prepare_category_execution_configuration(
            source,
            admitted,
            frozen.inputs,
            private,
            scope,
            site,
            acquisition,
            environment,
            operation,
            operation.model_copy(update={"operation_id": "execution.run-read"}),
            evidence=evidence,
            controls=controls,
            prefix="execution",
            metadata_cleanup_seconds=frozen.run.resources.cleanup_timeout_seconds,
            physical_close_seconds=physical_close_seconds,
        )
        runs = FileRunJournal(
            run_root,
            frozen.binding,
            controls,
            evidence,
            capacity=frozen.run.run_capacity,
        )
        first = operation.model_copy(update={"operation_id": "run.planned"})
        snapshot = runs.create(
            RunEvent(
                stage="planned",
                operation=first,
                occurred_at=clock.utcnow(),
                component_id="original-allocation-controller",
                job_id=execution.job_id,
                inputs=(frozen.binding.plan_ref,),
                outputs=(accounting_ref,),
            ),
            first,
        )
        stages: tuple[RunStage, ...] = (
            "validated",
            "claimed",
            "submitting",
            "submitted",
            "running",
        )
        for stage in stages:
            record, _ = snapshot.project()
            current = operation.model_copy(update={"operation_id": "run." + stage})
            event = RunEvent(
                stage=stage,
                operation=current,
                previous_operation_id=record.events[-1].operation.operation_id,
                occurred_at=clock.utcnow(),
                component_id="original-allocation-controller",
                job_id=execution.job_id,
                inputs=(frozen.binding.plan_ref, admitted.claim.reference),
                outputs=(accounting_ref,),
                submission=(
                    SubmissionObservation(
                        submission_key=frozen.binding.submission_key,
                        outcome="accepted",
                        job_ids=(execution.job_id,),
                        evidence=(accounting_ref,),
                    )
                    if stage == "submitted"
                    else None
                ),
            )
            snapshot = runs.append(RunEntry(event=event), snapshot.revision, current)
        sources = ExecutionTaskPhaseSources(admitted.reader)
        owner = ClaimedRunResourceOwner(
            admitted.authority,
            admitted.claim.reference,
            declarations.plan.read_operation,
            claims=admitted.claims,
            runs=runs,
            plans=admitted.plans,
            evidence=evidence,
            task_plan=declarations.plan,
            sources=sources,
            source_run_reads=sources,
        )
        return ClaimedCategoryNavigationMember(admitted, declarations, owner)
    except BaseException as error:
        if admitted is not None:
            setattr(error, "category_original_admitted_source", admitted)
        raise
