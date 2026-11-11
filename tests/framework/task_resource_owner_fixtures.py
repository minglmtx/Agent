"""Current default task with explicit synthetic claim/kernel/model/site premises.

Production suppliers are installed below. Only the original Slurm caller and
process-observation edge are synthetic; no real task or runtime permission.
"""

from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import replace
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast, Any
import pytest
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
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceContexts
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.ledger.task_trace_authority import (
    OriginalTaskTraceAuthority,
)
from lab_generate_skill.adapters.plans.trace_journal_evidence import (
    TraceJournalEvidence,
)
from lab_generate_skill.bootstrap.task_actor import TaskActorResources
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.adapters.models.task_actor_authority import (
    OriginalTaskActorAuthority,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.domain.local_actor import LocalActorBinding
from lab_generate_skill.adapters.plans.task_context_authority import (
    OriginalTaskContextAuthority,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
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
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.bootstrap.map_task_execution import (
    map_navigation_task_execution,
    MapExecutionTaskRuntime,
)
from lab_generate_skill.bootstrap.map_task_execution_bindings import (
    MapTaskExecutionDeclarations,
    MapTaskExecutionResources,
    MapExecutionTaskAuthorities,
    TaskInitialBinding,
)
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.sites.map.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from lab_generate_skill.sites.map.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from map_execution_task_fixtures import (
    single_map_execution_case,
    SingleMapExecutionCase,
)
from map_task_execution_initialization_fixtures import current_initial_binding
from map_task_execution_actor_fixtures import current_map_actor_resources
import lab_generate_skill.adapters.sites.task_resource_owner as resource_module


class UnitModelScope(ActorExecutionScope):
    """Explicit synthetic model/physical permission edge for this combination.

    The real ActorExecutionScope installation/kernel behavior has its own
    registered-resource tests. This does not qualify a production model.
    """

    def __init__(self, original: Any) -> None:
        self.original = original
        self.spec, self.binding, self.engine = (
            original.spec,
            original.binding,
            original.engine,
        )
        self.guard, self.evidence = original.guard, original.evidence
        self.acquisition_reads = None

    def require_original(
        self,
        binding: LocalActorBinding,
        operation: OperationContext,
        control: OperationControl,
        *,
        live: bool,
    ) -> None:
        self.original.require_original(binding, operation, control, live=live)


@contextmanager
def owned_task(
    root: Path,
    patch: pytest.MonkeyPatch,
    *,
    input_handoff: bool = False,
    capture_initial_handoff: bool = False,
) -> Iterator[tuple[SingleMapExecutionCase, OriginalTaskResourceOwner]]:
    if capture_initial_handoff and not input_handoff:
        raise ValueError("Capture body fixture requires the original owned input scope")
    with single_map_execution_case(root, patch, "125732d3658ab4daee02") as c:
        c.native.scope = UnitModelScope(c.native.scope)
        p, j, h = c.p, c.journals, c.handles
        store, controls = p.original.resource.evidence, p.original.resource.controls
        run = j.plans.load(p.plan.intent.binding.run, p.plan.read_operation)
        task = run.tasks[0]
        physical = p.original.resource.spec.slurm
        caller_identity = os.getpid(), threading.get_ident()

        assert isinstance(j.source_reader.contexts, EvidenceContextRecords)
        closed_contexts = ClosedMapSourceContexts(
            j.source_reader.contexts, j.source_ref
        )
        j.source_reader.contexts = closed_contexts

        class Caller(OriginalExecutionClaimAuthority):
            def __init__(self) -> None:
                self.run, self.task = p.plan.intent.binding.run, task
                self.execution, self.controller = physical.execution, physical.parent
                # Explicit unit physical/source premise. Production constructs
                # this class through its actual kernel-checked constructor.
                self.contexts = closed_contexts

            def require_caller(self, op: OperationContext) -> None:
                controls.bind(op).checkpoint()
                if caller_identity != (os.getpid(), threading.get_ident()) or (
                    op.run_id,
                    op.owner_id,
                ) != (self.run.owner.run_id, self.run.owner.owner_id):
                    raise OwnershipConflict("Explicit unit original caller changed")

        owner = ClaimedRunResourceOwner(
            Caller(),
            p.plan.intent.binding.claim_ref,
            p.plan.read_operation,
            claims=j.claims,
            runs=j.runs,
            plans=j.plans,
            evidence=store,
            task_plan=p.plan,
            sources=ExecutionTaskPhaseSources(j.source_reader),
        )
        holder = OriginalTaskBrowserOwner(
            p.reset.attempt_allocations[0], p.original.resource.journal
        )
        assert isinstance(p.site, RetainedSiteResource)
        site = p.site
        inputs = TaskInitializationInputs(p.plan) if input_handoff else None
        r = OriginalTaskResourceOwner(
            owner, p.plan, site, holder, c.native.scope, inputs=inputs
        )

        def observe(
            execution: object, worker: object, control: OperationControl
        ) -> SimpleNamespace:
            control.checkpoint()
            if (
                site.phase == "open"
                and worker == site.site.ready.worker.owner_guard.worker
            ):
                return SimpleNamespace(
                    membership=site.site.ready.controller.target.worker
                )
            b = holder.original()
            assert b is not None
            record = b.journal.read(b.spec.token, b.operation)
            from lab_generate_skill.domain.browser_worker_acquisition import (
                BrowserWorkerAcquiredFact,
            )

            fact = BrowserWorkerAcquiredFact.model_validate_json(
                store.read(record.events[2].evidence[0], control)
            )
            assert worker == fact.details.prepared.owner_guard.worker
            return SimpleNamespace(
                membership=fact.details.prepared.step.controller.target.worker
            )

        patch.setattr(resource_module, "observe_process_cgroup", observe)
        old = c.bundle
        d = MapTaskExecutionDeclarations(
            p.plan,
            p.declaration,
            p.reset,
            old.capture.declaration,
            old.capture.declaration_ref,
            old.finalization.declaration,
            old.finalization.declaration_ref,
        )

        def initial_checks() -> InitialObservationChecks:
            current = c.bundle.initialization.original()
            measurement = current.measurements
            assert isinstance(measurement, CapturedTaskInitialMeasurements)
            capture = measurement.capture
            assert (
                capture is not None
                and capture.intent_ref is not None
                and capture.result_ref is not None
            )
            b = holder.original()
            assert b is not None
            selected = b.spec.configuration.initialization
            assert isinstance(selected, MapNavigationInitialization)
            return NavigationInitialObservationChecks(
                store,
                MapInitialEvidence(
                    intent_ref=capture.intent_ref, result_ref=capture.result_ref
                ),
                selected,
            )

        def initial(
            prep: object, op: OperationContext, control: OperationControl
        ) -> TaskInitialBinding:
            holder.begin()
            selected = current_initial_binding(
                p, j, c.native, h, patch, c.bundle.preparation, op, control
            )
            if inputs is not None:
                from lab_generate_skill.adapters.browsergym.prepared_authority import (
                    PreparedBrowserAuthority,
                )
                from lab_generate_skill.adapters.browsergym.return_publication import (
                    BrowserReturnPublication,
                )

                authority = selected.browser.authority
                assert isinstance(authority, PreparedBrowserAuthority)
                authority.binding.inputs = inputs
                selected.browser.return_publication = BrowserReturnPublication(
                    selected.browser.spec.token, controls, p.original.resource.clock, 30
                )
            holder.retain(selected.browser)
            q = c.bundle.preparation.qualifications
            assert isinstance(q, EvidenceStateQualifications)
            contexts = OriginalTaskContextAuthority(
                r,
                c.bundle.preparation,
                c.bundle.initialization.original,
                j.source_ref,
                j.source_reader.contexts,
                controls,
                states=q.checks,
                initial_checks=initial_checks,
                comparison=NavigationInitialComparison(),
                inputs=inputs,
            )
            return replace(
                selected,
                state=contexts,
                context=contexts,
                capture=OriginalTaskBrowserCaptureAuthority(
                    r,
                    c.bundle.initialization.original,
                    lambda: c.bundle.capture,
                    lambda: h.trace,
                ),
                initial=OriginalTaskInitialAuthority(r, initial_checks),
                inputs=inputs,
            )

        def actors(
            initialized: InitializedTask, prepared: PreparedActorInput
        ) -> TaskActorResources:
            value = current_map_actor_resources(p, c.native, h, initialized, prepared)
            assert isinstance(value.journal, FileTraceJournal)
            # Replace the existing fixture's synthetic provenance hook at its
            # documented journal authority edge, before any Actor intent.
            value.journal.verifier = TraceJournalEvidence(
                store,
                OriginalTaskTraceAuthority(
                    r, value.journal.plan, lambda: tuple(value.completed)
                ),
            )
            return value

        resources = MapTaskExecutionResources(
            p.original.resource.spec,
            p.site,
            p.original.resource.journal,
            p.original.resource.journal,
            p.source.native.bindings,
            holder.original,
            lambda: h.trace,
            initial,
            actors,
            cast(TaskSiteAuthority, p.site.authority),
        )
        runtime = MapExecutionTaskRuntime(
            j.source_reader,
            j.runs,
            j.claims,
            OriginalExecutionTaskAuthority(r),
            store,
            controls,
            p.original.resource.clock,
            j.plans,
        )
        final = OriginalTaskFinalizationAuthority(r, lambda: c.bundle.finalization)
        actor_source = OriginalTaskActorAuthority(
            r, lambda: c.bundle.initialization.original(), lambda: h.trace
        )
        c.bundle = map_navigation_task_execution(
            d,
            resources,
            MapExecutionTaskAuthorities(
                final, OriginalTaskNonstartAuthority(r), actor_source
            ),
            runtime,
            initial_inputs=inputs if capture_initial_handoff else None,
        )
        if inputs is not None:
            original_scope = c.bundle.task.resource_scope
            assert original_scope is not None

            @contextmanager
            def input_scope() -> Iterator[object]:
                assert inputs is not None and original_scope is not None
                with j.source_reader.task_scope(p.plan), inputs.scope():
                    with original_scope() as value:
                        yield value

            c.bundle.task.resource_scope = input_scope
        p.preparation = c.bundle.preparation
        yield c, r
