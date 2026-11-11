"""Actual claimed owners and one original task lifecycle, with explicit site policy.

This is the unchanged resource/Actor/trace assembly extracted from Map. It does
not qualify a source, create a claim, acquire a worker or implement a runner.
Only prepared/initial/equivalence codecs and the site composition are injected.
"""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.sites.task_preparation_inputs import (
    TaskPreparationDeclarationInputs,
)


from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.browsergym.claimed_authority import (
    ClaimedBrowserResourceAuthority,
)
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.return_publication import (
    BrowserReturnPublication,
)
from lab_generate_skill.adapters.browsergym.task_owner import OriginalTaskBrowserOwner
from lab_generate_skill.adapters.browsergym.task_capture_authority import (
    OriginalTaskBrowserCaptureAuthority,
)
from lab_generate_skill.adapters.browsergym.task_initial_authority import (
    OriginalTaskInitialAuthority,
)
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.ledger.task_trace_authority import (
    OriginalTaskTraceAuthority,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.task_actor_authority import (
    OriginalTaskActorAuthority,
)
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.plans.task_context_authority import (
    OriginalTaskContextAuthority,
)
from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.execution_task_authority import (
    OriginalExecutionTaskAuthority,
)
from lab_generate_skill.adapters.sites.task_nonstart_authority import (
    OriginalTaskNonstartAuthority,
)
from lab_generate_skill.adapters.sites.task_finalization_authority import (
    OriginalTaskFinalizationAuthority,
)
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskOriginSource,
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControls,
    OperationControl,
    ResourceJournal,
)
from lab_generate_skill.ports.task_bindings import TaskBindings
from .execution_task import RecordedExecutionTask
from .task_execution_bindings import (
    TaskExecutionDeclarations,
    TaskExecutionResources,
    ExecutionTaskAuthorities,
    TaskInitialBinding,
)
from .task_actor import TaskActorResources
from .owned_preparation_records import owned_preparation_records


from typing import Generic, Protocol, TypeVar
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_finalization import RecordedTaskFinalization
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.ports.site_resources import (
    SiteOriginAuthority,
    SiteResourceAuthority,
)
from lab_generate_skill.ports.task_initialization import TaskInitialComparison


@dataclass(frozen=True)
class TaskBrowserDeclarations:
    spec: BrowserResourceSpec
    initial: TaskInitializationPlan
    initial_ref: EvidenceRef


class OwnedTaskInitialization(Protocol):
    """Read only the original initializer; its concrete producer stays invariant."""

    def original(self) -> RecordedTaskInitialization: ...


class OwnedTaskBundle(Protocol):
    # Existing site bundles are frozen dataclasses. Assembly only reads them;
    # mutable protocol members would incorrectly reject those original bundles.
    @property
    def task(self) -> RecordedExecutionTask: ...
    @property
    def preparation(self) -> RecordedSiteTaskPreparation: ...
    @property
    def initialization(
        self,
    ) -> OwnedTaskInitialization: ...
    @property
    def capture(self) -> RecordedTaskCapture: ...
    @property
    def finalization(self) -> RecordedTaskFinalization: ...


BundleT = TypeVar("BundleT", bound=OwnedTaskBundle)


@dataclass(frozen=True)
class OwnedTaskExecution(Generic[BundleT]):
    bundle: BundleT
    resources: OriginalTaskResourceOwner
    physical_site: ObservedSiteResourceAuthority


@dataclass(frozen=True)
class OwnedTaskPolicy:
    site_rights: Callable[
        [ClaimedRunResourceOwner, SiteResourceSpec, OperationContext],
        SiteResourceAuthority,
    ]
    origin: SiteOriginAuthority | None
    prepared_checks: Callable[
        [EvidenceStore, SiteResourceSpec, SiteResourceStarted],
        PreparedBrowserTaskChecks,
    ]
    initial_checks: Callable[
        [EvidenceStore, BrowserResourceSpec, EvidenceRef, EvidenceRef],
        InitialObservationChecks,
    ]
    comparison: TaskInitialComparison
    metadata_cleanup_seconds: int | None = None

    def __post_init__(self) -> None:
        value = self.metadata_cleanup_seconds
        if value is not None and (type(value) is not int or not 1 <= value <= 3600):
            raise ValueError("Explicit bounded component metadata cleanup required")


def owned_task_execution(
    declarations: TaskExecutionDeclarations,
    owner: ClaimedRunResourceOwner,
    source: OriginalExecutionTaskSource,
    model: ActorExecutionScope,
    site_spec: SiteResourceSpec,
    site_acquisition: OperationContext,
    browser_declarations: Callable[
        [RecordedSiteTaskPreparation, OperationContext, OperationControl],
        TaskBrowserDeclarations,
    ],
    *,
    journal: ResourceJournal,
    bindings: TaskBindings,
    controls: OperationControls,
    clock: Clock,
    trace_root: Path,
    calls_root: Path,
    trace_capacity: TraceCapacity,
    policy: OwnedTaskPolicy,
    compose: Callable[
        [
            TaskExecutionDeclarations,
            TaskExecutionResources,
            ExecutionTaskAuthorities,
            OriginalTaskResourceOwner,
        ],
        BundleT,
    ],
) -> OwnedTaskExecution[BundleT]:
    if (
        not isinstance(declarations, TaskExecutionDeclarations)
        or not isinstance(owner, ClaimedRunResourceOwner)
        or not isinstance(source, OriginalExecutionTaskSource)
        or not isinstance(model, ActorExecutionScope)
        or not callable(browser_declarations)
        or not isinstance(policy, OwnedTaskPolicy)
        or not callable(policy.site_rights)
        or not callable(policy.prepared_checks)
        or not callable(policy.initial_checks)
        or policy.comparison is None
        or not callable(compose)
    ):
        raise TypeError(
            "Typed original source/claim/model and pure browser declaration factory required"
        )
    if (
        not isinstance(owner.authority, OriginalExecutionClaimAuthority)
        or not isinstance(source.contexts, ClosedSourceContexts)
        or owner.authority.contexts is not source.contexts
        or not isinstance(owner.sources, ExecutionTaskPhaseSources)
        or owner.sources.source is not source
        or declarations.plan != owner.task_plan
        or source.claims is not owner.claims
        or source.plans is not owner.plans
    ):
        raise OwnershipConflict(
            "Production task owners require the same original closed source/claim/plan readers"
        )
    evidence, plan = owner.evidence, declarations.plan
    sources = owner.sources
    source_rights = policy.site_rights(owner, site_spec, site_acquisition)
    physical = ObservedSiteResourceAuthority(
        site_spec, site_acquisition, source=source_rights, evidence=evidence
    )
    native_source = TaskSiteAuthority(
        site_spec, site_acquisition, physical, origin=policy.origin
    )
    site = RetainedSiteResource(
        site_spec,
        site_acquisition,
        journal=journal,
        evidence=evidence,
        controls=controls,
        clock=clock,
        authority=native_source,
        cleanup_seconds=(
            plan.cleanup_seconds
            if policy.metadata_cleanup_seconds is None
            else policy.metadata_cleanup_seconds
        ),
    )
    if len(declarations.reset.attempt_allocations) != 1:
        raise OwnershipConflict("Exactly one original attempt browser required")
    browser_owner = OriginalTaskBrowserOwner(
        declarations.reset.attempt_allocations[0], journal
    )
    task_inputs = TaskInitializationInputs(declarations.plan)
    resources = OriginalTaskResourceOwner(
        owner, plan, site, browser_owner, model, inputs=task_inputs
    )
    bundle: BundleT
    trace: FileTraceJournal | None = None
    completed: list[LocalActorExecution] = []

    def original_trace() -> FileTraceJournal:
        if trace is None:
            raise OwnershipConflict("Original task trace has not been constructed")
        return trace

    def initial_checks() -> InitialObservationChecks:
        initial = bundle.initialization.original()
        measurement = initial.measurements
        if (
            not isinstance(measurement, CapturedTaskInitialMeasurements)
            or measurement.capture is None
            or measurement.capture.intent_ref is None
            or measurement.capture.result_ref is None
        ):
            raise OwnershipConflict(
                "Original initial capture result required before checking"
            )
        b = browser_owner.original()
        if b is None:
            raise OwnershipConflict("Original selected browser required")
        return policy.initial_checks(
            evidence,
            b.spec,
            measurement.capture.intent_ref,
            measurement.capture.result_ref,
        )

    def initial(
        prep: RecordedSiteTaskPreparation,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskInitialBinding:
        browser_owner.begin()
        declared = browser_declarations(prep, operation, control)
        if not isinstance(declared, TaskBrowserDeclarations):
            raise TypeError("Pure typed original browser declarations required")
        spec, d = declared.spec, declared.initial
        if (
            not isinstance(spec, BrowserResourceSpec)
            or not isinstance(d, TaskInitializationPlan)
            or d.browser_acquisition.mode != "execute"
            or d.source_context_receipt_ref
            != owner.task_source(operation, control).context_receipt_ref
            or d.actor.model_allocation != model.binding.resource
        ):
            raise OwnershipConflict(
                "Browser declaration changed original source/model/acquisition"
            )
        if (
            owner.reads.read(d.browser_spec_ref, control)
            != spec.model_dump_json().encode()
            or owner.reads.read(declared.initial_ref, control)
            != d.model_dump_json().encode()
        ):
            raise OwnershipConflict(
                "Original immutable browser/initialization declaration bytes required"
            )
        prepared = prep.state.result
        if prepared is None:
            raise OwnershipConflict(
                "Actual original preparation must finish before browser declaration"
            )
        binding = PreparedBrowserBinding(
            prepared.publication,
            site_spec,
            site.site,
            site_acquisition,
            evidence=evidence,
            preparations=prep.records,
            journal=journal,
            task_checks=policy.prepared_checks(evidence, site_spec, site.site),
            inputs=task_inputs,
        )
        browser = RetainedBrowserResource(
            spec,
            d.browser_acquisition,
            journal=journal,
            evidence=evidence,
            controls=controls,
            clock=clock,
            cleanup_seconds=plan.cleanup_seconds,
            return_publication=BrowserReturnPublication(
                spec.token, controls, clock, d.actor.cleanup_seconds
            ),
            authority=PreparedBrowserAuthority(
                spec,
                binding,
                ClaimedBrowserResourceAuthority(owner, spec, d.browser_acquisition),
            ),
        )
        browser_owner.retain(browser)
        q = prep.qualifications
        if not isinstance(q, EvidenceStateQualifications):
            raise OwnershipConflict("Original state qualification producer required")
        from .current_initial_adoption import stage_initial_adoption_checks

        adoption_checks = stage_initial_adoption_checks(
            plan, d.scope, source, operation, controls
        )
        context = OriginalTaskContextAuthority(
            resources,
            prep,
            bundle.initialization.original,
            d.source_context_receipt_ref,
            source.contexts,
            controls,
            states=q.checks,
            initial_checks=initial_checks,
            comparison=policy.comparison,
            inputs=task_inputs,
        )
        return TaskInitialBinding(
            d,
            declared.initial_ref,
            browser,
            context,
            context,
            OriginalTaskBrowserCaptureAuthority(
                resources,
                bundle.initialization.original,
                lambda: bundle.capture,
                original_trace,
            ),
            OriginalTaskInitialAuthority(resources, initial_checks),
            task_inputs,
            adoption_checks,
        )

    def actor(
        initialized: InitializedTask, prepared: PreparedActorInput
    ) -> TaskActorResources:
        nonlocal trace
        if trace is not None:
            raise DispatchAlreadyCommitted(
                "Original task Actor/trace binding is one-shot"
            )
        request = initialized.actor
        b = resources.require_browser(
            request.operation, controls.bind(request.operation)
        )
        run = owner.plans.load(owner.run, plan.read_operation)
        tp = TracePlan(
            binding=prepared.binding,
            scope=request.scope,
            initial_observation_ref=request.initial_observation_ref,
            max_generations=run.resources.max_actor_generations_per_attempt,
            max_interactions=run.resources.max_interactions_per_attempt,
            capacity=trace_capacity,
        )
        trace_root.mkdir()
        calls_root.mkdir()
        trace = FileTraceJournal(
            trace_root,
            tp,
            controls,
            evidence,
            OriginalTaskTraceAuthority(resources, tp, lambda: tuple(completed)),
        )
        trace.create(
            tp,
            request.operation.model_copy(
                update={
                    "operation_id": request.operation.operation_id
                    + ".original-trace-create"
                }
            ),
        )
        return TaskActorResources(model, b.session, trace, calls_root, completed)

    authorities = ExecutionTaskAuthorities(
        OriginalTaskFinalizationAuthority(resources, lambda: bundle.finalization),
        OriginalTaskNonstartAuthority(resources),
        OriginalTaskActorAuthority(
            resources, lambda: bundle.initialization.original(), original_trace
        ),
    )
    supplied = TaskExecutionResources(
        site_spec,
        site,
        journal,
        journal,
        bindings,
        browser_owner.original,
        original_trace,
        initial,
        actor,
        native_source,
    )
    bundle = compose(declarations, supplied, authorities, resources)
    declaration_inputs = TaskPreparationDeclarationInputs(
        plan, declarations.preparation, task_inputs, source.contexts
    )
    task_inputs.preparation_declarations = declaration_inputs
    bundle.preparation.bind_declared_inputs(declaration_inputs)
    bundle.preparation.records = owned_preparation_records(
        bundle.preparation.records, source.contexts, inputs=task_inputs
    )
    original_scope = bundle.task.resource_scope
    if original_scope is None:
        raise OwnershipConflict("Original retained site scope required")

    @contextmanager
    def physical_scope() -> Iterator[object]:
        # Observation handles outlive task finalization and the original site's
        # close, including failures before bookkeeping can call its authority.
        from contextlib import nullcontext
        from lab_generate_skill.adapters.plans.closed_actor_inputs import (
            SupervisedActorAcquisitionReads,
        )

        acquisition_reads = model.acquisition_reads
        acquisition_scope = (
            acquisition_reads.task_scope(plan.operation)
            if isinstance(acquisition_reads, SupervisedActorAcquisitionReads)
            else nullcontext()
        )
        with source.task_scope(plan), task_inputs.scope(), acquisition_scope:
            with physical:
                with original_scope():
                    yield site

    bundle.task.resource_scope = physical_scope
    return OwnedTaskExecution(bundle, resources, physical)
