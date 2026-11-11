"""Final category entry over original source, claim, model and sole task ports.

The physical supplier provides this exact actual owner/runtime. This entry adds
no source permission, lifecycle loop, retry or default resume capability.
"""

from dataclasses import dataclass
from pathlib import Path
from contextlib import nullcontext
from lab_generate_skill.application.execution_stage import execution_stage
import time
from typing import Any
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.policies.actor_entry_budget import checked_actor_round_budgets
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.shopping_navigation_origin import ShoppingCategoryOrigin
from lab_generate_skill.domain.site_resource import SiteSlurmBinding
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.ports.lifecycle import Clock, OperationControls, ResourceJournal
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from .shopping_category_actor_configuration import publish_category_actor_inputs
from .shopping_category_run_configuration import freeze_category_execution_run
from .shopping_category_source_artifact import consume_category_navigation_source
from .shopping_category_source_qualification import qualify_category_navigation_source
from .shopping_category_production_site import declare_category_production_site
from .shopping_category_production_admission import admit_category_production_member
from .shopping_category_production_member import (
    execute_claimed_category_member,
    CategoryNavigationMemberCompletion,
)
from .shopping_category_navigation import load_category_navigation_inputs
from .shopping_category_source_inputs import CategorySourceReuseInputs
from .source_browser_assets import SourceBrowserAssets
from .shopping_category_source_publication import PublishedCategoryNavigationSource
from lab_generate_skill.policies.publication_inputs import checked_publication_inputs
from .shopping_category_member_review import review_completed_category_member


@dataclass(frozen=True)
class CategoryNavigationProductionRuntime:
    owner: OriginalSourceQualificationOwner
    scope: StateScope
    operation: OperationContext
    model: ActorResourceSpec
    model_operation: OperationContext
    binding: ActorModelBinding
    parameters: LocalActorParameters
    software_ref: EvidenceRef
    software: bytes
    template: BrowserWorkerConfiguration | None
    browser_assets: SourceBrowserAssets
    source_reads: ClosedSourceReadTransport
    journal: ResourceJournal
    controls: OperationControls
    clock: Clock
    allocation_verifier: SlurmAllocationVerifier
    output: Path
    workspace_root: Path
    source_node_root: Path
    candidate_node_root: Path
    claim_root: Path
    claim_scope: str
    origin: ShoppingCategoryOrigin
    accounting_ref: EvidenceRef
    image: ReleaseFile
    image_source: Path
    site_seconds: int
    task_seconds: int
    setup_seconds: int
    source_metadata_seconds: int
    metadata_cleanup_seconds: int
    physical_close_seconds: int
    generation_seconds: int
    interaction_seconds: int
    actor_cleanup_seconds: int
    source_recovery_budgets: SourceRecoveryBudgets
    retained_source: ClosedCategoryNavigationReadMaterial | None = None
    verified_source: PublishedCategoryNavigationSource | None = None
    source_installation: ReleaseInstallation | None = None
    generation_budgets: ActorGenerationBudgets | None = None
    source_inputs: CategorySourceReuseInputs | None = None

    @property
    def declared_installation(self) -> ReleaseInstallation:
        """Static installation declaration; source preparation supplies real refs."""
        installation = self.source_installation
        if installation is None:
            if self.template is None:
                raise ValueError("Category source installation declaration required")
            installation = self.template.installation
        installation = ReleaseInstallation.model_validate(installation)
        if self.template is not None and self.template.installation != installation:
            raise OwnershipConflict("Category browser/source installation mismatch")
        return installation


def run_category_production(
    runtime: CategoryNavigationProductionRuntime,
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
    facts: dict[str, Any],
) -> CategoryNavigationMemberCompletion:
    if not isinstance(runtime, CategoryNavigationProductionRuntime):
        raise TypeError("Actual category production runtime required")
    r = runtime
    installation = r.declared_installation
    selected = (
        load_category_navigation_inputs(raw, native_ref, public)
        if r.source_inputs is None
        else r.source_inputs.require(raw, native_ref, public)
    )
    if (
        not isinstance(r.controls, BoundedOperationControls)
        or r.owner.scope.owner != r.scope.owner
        or r.owner.scope.task != r.scope.task
        or r.owner.scope.attempt_id == r.scope.attempt_id
        or selected.private_spec.task != r.scope.task
        or r.model.token.owner != r.scope.owner
        or r.source_reads.store is not r.owner.evidence
        or r.model.release_ref != installation.manifest_ref
        or public.start_url
        != r.origin.endpoint.rstrip("/") + selected.private_spec.original.start_path
        or r.scope.owner.job_id != r.owner.execution.job_id
    ):
        raise OwnershipConflict(
            "Category entry changed actual source/runtime/model/task"
        )
    for value, maximum in (
        (r.site_seconds, 7200),
        (r.task_seconds, 14400),
        (r.setup_seconds, 14400),
        (r.source_metadata_seconds, 1800),
        (r.metadata_cleanup_seconds, 3600),
        (r.physical_close_seconds, 60),
        (r.generation_seconds, 600),
        (r.interaction_seconds, 180),
        (r.actor_cleanup_seconds, 60),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("Explicit bounded category runtime budgets required")
    if r.physical_close_seconds > r.metadata_cleanup_seconds:
        raise ValueError("Metadata cleanup must cover physical category close")
    generation_budgets = checked_actor_round_budgets(
        r.generation_budgets,
        r.generation_seconds,
        r.interaction_seconds,
        r.actor_cleanup_seconds,
        r.task_seconds,
    )
    store = r.owner.evidence
    control = r.controls.bind(r.operation)
    r.owner.require(r.operation, control, new_work=r.retained_source is None)
    facts.update(
        phase="actor_configuration",
        engineering_only=True,
        formal_training_qualification=False,
        source_task_id=r.scope.task.source_task_id,
        paid_calls=0,
    )
    inputs = publish_category_actor_inputs(
        r.model,
        r.binding,
        r.parameters,
        r.software_ref,
        r.software,
        store,
        r.operation,
        control,
    )
    actor = TaskActorInitialization(
        candidate_id=inputs.policy.candidate_id,
        revision_round=0,
        context_configuration_ref=inputs.context_ref,
        memory=inputs.policy.memory,
        model_allocation=r.model.token,
        parameters_refs=(inputs.parameters_ref,) * 20,
        generation_seconds=r.generation_seconds,
        generation_budgets=generation_budgets,
        interaction_seconds=r.interaction_seconds,
        cleanup_seconds=r.actor_cleanup_seconds,
    )
    slurm = SiteSlurmBinding(
        execution=r.owner.execution,
        parent=r.owner.controller,
        srun_executable="/usr/bin/srun",
        scontrol_executable="/usr/bin/scontrol",
    )
    facts["phase"] = "source_qualification"
    before = time.monotonic()
    with (
        execution_stage(
            r.controls,
            "source",
            r.operation,
            seconds=(
                r.source_metadata_seconds if r.retained_source is not None else None
            ),
        )
        if r.verified_source is None
        else nullcontext()
    ):
        if r.retained_source is not None:
            if r.verified_source is None:
                qualified = consume_category_navigation_source(
                    r.owner,
                    r.retained_source,
                    raw,
                    native_ref,
                    public,
                    r.operation,
                    r.controls,
                    r.source_reads,
                )
            else:
                qualified = r.verified_source
                checked = checked_publication_inputs(
                    qualified.material.context_ref, qualified.receipt, qualified.inputs
                )
                if (
                    qualified.material != r.retained_source
                    or qualified.receipt.scope != r.owner.scope
                    or checked.context.task != public
                ):
                    raise OwnershipConflict(
                        "Same-call category source body changed original material/scope/task"
                    )
                r.owner.require(r.operation, control, new_work=False)
            facts["source_qualification_mode"] = (
                "consume_existing_qualified_task_source"
            )
        else:
            if r.verified_source is not None:
                raise OwnershipConflict(
                    "Same-call category source body requires its full original material"
                )
            source = declare_category_production_site(
                raw,
                native_ref,
                public,
                r.owner.scope,
                installation,
                slurm,
                r.origin,
                r.image,
                r.image_source,
                r.source_node_root,
                r.operation,
                evidence=store,
                controls=r.controls,
                clock=r.clock,
                prefix="source",
                site_seconds=r.site_seconds,
                defer_acquisition=False,
            )
            qualified = qualify_category_navigation_source(
                r.owner,
                source.spec,
                source.acquisition,
                raw,
                native_ref,
                source.public,
                r.browser_assets,
                journal=r.journal,
                controls=r.controls,
                clock=r.clock,
                prefix="source",
                metadata_seconds=r.source_metadata_seconds,
                source_reads=r.source_reads,
                recovery_budgets=r.source_recovery_budgets,
                publication_root=r.operation,
            )
            facts["source_qualification_mode"] = "construct_task_specific_source"
    facts.update(
        source_prefix_reuse=qualified.source_prefix_reuse,
        source_qualified=True,
        source_qualification_seconds=facts.get("retained_source_read_seconds", 0)
        + time.monotonic()
        - before,
        closed_source_context_ref=qualified.material.context_ref.model_dump(
            mode="json"
        ),
    )
    if qualified.inputs.context.task != public:
        raise OwnershipConflict(
            "Category source changed selected actual public target/start"
        )
    template = qualified.material.browser.configuration
    if template.installation != installation:
        raise OwnershipConflict("Qualified category source changed installation")
    candidate = declare_category_production_site(
        raw,
        native_ref,
        public,
        r.scope,
        installation,
        slurm,
        r.origin,
        r.image,
        r.image_source,
        r.candidate_node_root,
        r.operation,
        evidence=store,
        controls=r.controls,
        clock=r.clock,
        prefix="execution",
        site_seconds=r.site_seconds,
        defer_acquisition=True,
        baseline_ref=qualified.inputs.baseline_inputs.binding.baseline_ref,
    )
    frozen = freeze_category_execution_run(
        qualified,
        r.scope,
        r.model,
        r.parameters,
        inputs,
        r.operation,
        owner=r.owner,
        evidence=store,
        controls=r.controls,
        task_seconds=r.task_seconds,
        cleanup_seconds=r.metadata_cleanup_seconds,
    )
    facts["pre_claim_remaining_seconds"] = r.controls.require_execution_budget(
        r.operation, preparation_seconds=r.setup_seconds, task_seconds=r.task_seconds
    )
    facts["phase"] = "source_claim_admission"
    member = admit_category_production_member(
        qualified,
        frozen,
        selected.private_spec,
        r.scope,
        candidate.spec,
        candidate.acquisition,
        candidate.environment,
        r.owner.execution,
        r.owner.controller,
        r.operation,
        run_root=r.output / "run",
        claim_root=r.claim_root,
        claim_scope=r.claim_scope,
        accounting_ref=r.accounting_ref,
        evidence=store,
        controls=r.controls,
        clock=r.clock,
        source_reads=r.source_reads,
        physical_close_seconds=r.physical_close_seconds,
    )
    facts["phase"] = "unified_task_lifecycle"
    try:
        completed = execute_claimed_category_member(
            member,
            qualified,
            candidate,
            r.model,
            r.model_operation,
            template,
            actor,
            journal=r.journal,
            controls=r.controls,
            clock=r.clock,
            allocation_verifier=r.allocation_verifier,
            output=r.output,
            workspace_root=r.workspace_root,
            site_seconds=r.site_seconds,
            task_seconds=r.task_seconds,
            source_reads=r.source_reads,
        )
    except BaseException as error:
        result = getattr(error, "category_task_result", None)
        executions = getattr(error, "category_model_executions", ())
        facts.update(
            phase_seconds=getattr(error, "category_phase_seconds", {}),
            actual_actor_members_executed=(
                [r.scope.task.source_task_id] if executions else []
            ),
            completed_model_exchanges=len(executions),
            **getattr(error, "category_input_reuse", {}),
        )
        if result is not None:
            facts.update(
                result=result.model_dump(mode="json"),
                business_result=result.evaluation.status,
            )
        raise
    facts.update(
        phase="closed_pending_independent_review",
        result=completed.result.model_dump(mode="json"),
        business_result=completed.result.evaluation.status,
        phase_seconds=completed.phase_seconds,
        task_preparation_stages=completed.preparation_stages,
        actual_actor_members_executed=(
            [r.scope.task.source_task_id] if completed.result.generations else []
        ),
        **(completed.input_reuse or {}),
    )
    review_completed_category_member(
        completed,
        installation.python_executable,
        r.output,
        r.operation,
        r.controls,
        r.clock,
        facts,
    )
    return completed
