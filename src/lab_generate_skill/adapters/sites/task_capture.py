"""Existing TaskCapture over original terminal, one browser owner and site guard.

The browser is closed through its original owner before a final native guard.
Later TaskFinalization only confirms that same closure, then restores separately.
"""

from collections.abc import Callable
import json
import os
import threading
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.domain.actor_run import ActorStop, ActorRunRequest
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    TaskCaptureResult,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.ports.task_capture import (
    TaskCaptureAuthority,
    TaskCaptureRecords,
)
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)
from lab_generate_skill.policies.task_capture import require_original_task_capture
from .recorded_capture import RecordedSiteCapture
from lab_generate_skill.ports.site_handle import SiteHandle
from .task_capture_state import TaskCaptureState


class TaskCaptureUnconfirmed(RuntimeError):
    def __init__(
        self,
        primary: BaseException,
        state: TaskCaptureState,
        writer: CaptureEvidence,
        failed_phase: str,
    ) -> None:
        self.primary, self.state, self.failed_phase = primary, state, failed_phase
        known = list(state.references)
        for name in (
            "reference",
            "capture_intent_reference",
            "capture_result_reference",
            "browser_resource_ending_ref",
        ):
            ref = getattr(primary, name, None)
            if isinstance(ref, EvidenceRef):
                known.append(ref)
        self.references = tuple(dict.fromkeys(known))
        candidates = [*state.candidates, *writer.candidates]
        for name in ("capture_candidate_references", "task_capture_record_candidates"):
            value = getattr(primary, name, ())
            if isinstance(value, tuple):
                candidates.extend(r for r in value if isinstance(r, EvidenceRef))
        self.candidates = tuple(dict.fromkeys(candidates))
        self.known_result = state.result
        super().__init__(
            "Original task capture unconfirmed; retain facts/owner and never redispatch"
        )


class RecordedTaskCapture:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskCapturePlan,
        declaration_ref: EvidenceRef,
        inputs: Callable[[OperationControl], TaskCaptureInputs],
        browser: Callable[[], RetainedBrowserResource],
        trace: Callable[[], TraceJournal],
        site: SiteHandle,
        site_spec: SiteResourceSpec,
        preparations: PreparationRecords,
        records: TaskCaptureRecords,
        authority: TaskCaptureAuthority,
        browser_authority: BrowserCaptureAuthority,
        site_authority: SiteCaptureAuthority,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        *,
        initials: InitialObservationReads | None = None,
    ) -> None:
        self.plan, self.declaration = TaskExecutionPlan.model_validate(
            plan
        ), TaskCapturePlan.model_validate(declaration)
        if any(
            x is None
            for x in (
                inputs,
                browser,
                trace,
                site,
                site_spec,
                preparations,
                records,
                authority,
                browser_authority,
                site_authority,
                evidence,
                controls,
                clock,
            )
        ):
            raise ValueError(
                "Original capture inputs/resources/authorities are mandatory"
            )
        self.declaration_ref, self.inputs, self.browser, self.trace = (
            declaration_ref,
            inputs,
            browser,
            trace,
        )
        if (
            declaration.metadata_close_seconds is not None
            and declaration.metadata_close_seconds > plan.cleanup_seconds
        ):
            raise ValueError(
                "Capture metadata budget exceeds frozen task cleanup budget"
            )
        self.site, self.site_spec, self.preparations, self.records = (
            site,
            site_spec,
            preparations,
            records,
        )
        self.authority, self.browser_authority, self.site_authority = (
            authority,
            browser_authority,
            site_authority,
        )
        self.evidence, self.controls, self.clock = evidence, controls, clock
        self.reads = StateReads(evidence)
        self.initials: InitialObservationReads = (
            InitialObservationReader(evidence, preparations)
            if initials is None
            else initials
        )
        self._initial_handoff_selected = initials is not None
        self.writer = CaptureEvidence(evidence, "task-capture-v1")
        self.state = TaskCaptureState()
        self.owner = os.getpid(), threading.get_ident()

    def _original(self, plan: TaskExecutionPlan) -> None:
        if self.owner != (os.getpid(), threading.get_ident()) or plan != self.plan:
            raise OwnershipConflict("Task capture changed original plan/controller")

    def preflight(
        self,
        plan: TaskExecutionPlan,
        requirements: EvidenceRequirements,
        control: OperationControl,
    ) -> None:
        self._original(TaskExecutionPlan.model_validate(plan))
        if self.state.phase not in ("new", "ready"):
            raise DispatchAlreadyCommitted("Original capture already attempted")
        d = self.declaration
        raw = self.reads.read(self.declaration_ref, control)
        require_complete_bytes(self.declaration_ref, raw)
        if (
            self.declaration_ref.content_schema,
            self.declaration_ref.visibility,
            self.declaration_ref.media_type,
        ) != (
            d.schema_version,
            "private",
            "application/json",
        ) or raw != d.model_dump_json().encode():
            raise OwnershipConflict("Frozen original task capture declaration changed")
        if (
            (d.scope.owner, d.scope.task, d.scope.attempt_id)
            != (
                plan.intent.binding.run.owner,
                plan.intent.binding.task,
                plan.intent.binding.attempt_id,
            )
            or requirements != d.requirements
            or requirements != plan.evaluation.requirements
        ):
            raise OwnershipConflict("Original capture scope/requirements changed")
        if d.close_seconds > plan.cleanup_seconds or plan.operation.operation_id in (
            d.page_operation_id,
            d.close_operation_id,
            d.guard_operation_id,
        ):
            raise OwnershipConflict("Capture changed original cleanup/operation bounds")
        control.checkpoint()
        self.state.phase = "ready"

    def capture(
        self,
        plan: TaskExecutionPlan,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskCaptureResult:
        plan, snapshot, operation = (
            TaskExecutionPlan.model_validate(plan),
            TraceSnapshot.model_validate(snapshot),
            OperationContext.model_validate(operation),
        )
        self._original(plan)
        if self.state.phase != "ready":
            raise DispatchAlreadyCommitted(
                "Preflight required; original capture cannot repeat"
            )
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
            operation.allocation_id,
            operation.recovery_ref,
            operation.cancellation_ref,
        ) != (
            plan.operation.run_id,
            plan.operation.owner_id,
            plan.operation.attempt_id,
            "execute",
            None,
            None,
            plan.operation.cancellation_ref,
        ) or operation.deadline > plan.operation.deadline:
            raise OwnershipConflict("Task capture changed original execute scope")
        s, d = self.state, self.declaration
        s.phase = "admission"
        try:
            # Re-read immutable declaration after preflight; resolve actual phase
            # results only now, never before native preparation/initialization.
            raw = self.reads.read(self.declaration_ref, control)
            require_complete_bytes(self.declaration_ref, raw)
            if raw != d.model_dump_json().encode():
                raise OwnershipConflict("Original capture declaration bytes changed")
            s.inputs = TaskCaptureInputs.model_validate(self.inputs(control))
            source, browser = s.inputs, self.browser()
            read_op = operation.model_copy(
                update={"operation_id": operation.operation_id + ".trace-read"}
            )
            if self.trace().read(read_op) != snapshot:
                raise OwnershipConflict("Original sealed TraceJournal changed")
            sealed = snapshot.project().sealed
            if sealed is None:
                raise OwnershipConflict("Original sealed Actor trace required")
            stop = self.reads.parse(
                sealed.stop_evidence_ref, "trace-stop/1", ActorStop, control
            )
            request = self.reads.parse(
                stop.request_ref,
                stop.request_ref.content_schema,
                ActorRunRequest,
                control,
            )
            require_original_task_capture(
                plan, d, source, snapshot, browser.spec, stop, request
            )
            if self._initial_handoff_selected:
                self.authority.verify(plan, d, source, snapshot, operation, control)
            initial = InitialObservationInputs.model_validate(
                self.initials.load(source.initial, operation, control)
            )
            session = browser.session
            if not isinstance(session.engine, SupervisedBrowserSession):
                raise OwnershipConflict("Original fixed registered browser required")
            returned = initial.acquired.details.started.initial_return_ref
            for turn in sealed.turns:
                if turn.interaction is not None and turn.interaction.result is not None:
                    returned = turn.interaction.result.return_ref
            if (
                initial.selection != source.initial
                or initial.prepared.public_task != source.initialized.actor.task
                or initial.prepared.task_binding_ref
                != plan.evaluation.task_contract_ref
                or initial.prepared.private_checks_ref
                != plan.evaluation.completion_spec_ref
                or initial.acquired.token != browser.spec.token
                or session.observation_ref != sealed.final_observation_ref
                or session.last_return_ref != returned
                or self.site.capture.configuration != self.site_spec.configuration
            ):
                raise OwnershipConflict(
                    "Capture changed actual original return/site/preparation"
                )
            self.authority.verify(plan, d, source, snapshot, operation, control)
            trace_ref = self.writer.put(
                sealed.model_dump_json().encode(), sealed.schema_version, control
            )
            snapshot_ref = self.writer.put(
                snapshot.model_dump_json().encode(), snapshot.schema_version, control
            )
            s.references.extend((trace_ref, snapshot_ref))
            s.phase = "page"
            page_op = plan.operation.model_copy(
                update={
                    "operation_id": d.page_operation_id,
                    "allocation_id": browser.spec.token.allocation_id,
                    "recovery_ref": browser.spec.token.recovery_ref,
                }
            )
            self.authority.verify(
                plan, d, source, snapshot, page_op, self.controls.bind(page_op)
            )
            page = RecordedBrowserCapture(
                session.engine, self.evidence, self.browser_authority
            )
            page_ref = page.capture(
                BrowserCaptureRequest(
                    scope=d.scope,
                    operation=page_op,
                    observation_sha256=sealed.final_observation_ref.sha256,
                    collector_id=d.page_collector_id,
                    collector_version=d.page_collector_version,
                ),
                control=self.controls.bind(page_op),
            )
            assert page.intent_ref is not None
            s.references.extend((page.intent_ref, page_ref))
            s.terminal_ref = self.records.terminal(
                source,
                trace_ref,
                snapshot_ref,
                returned,
                page.intent_ref,
                page_ref,
                operation,
                control,
            )
            s.references.append(s.terminal_ref)
            if self._initial_handoff_selected:
                self.authority.verify(plan, d, source, snapshot, operation, control)
            self.records.verify_terminal(s.terminal_ref, operation, control)
            s.phase = "browser-close"
            close_op = browser.operation.cleanup(
                d.close_operation_id,
                now=self.clock.utcnow(),
                seconds=(
                    d.close_seconds
                    if d.metadata_close_seconds is None
                    else d.metadata_close_seconds
                ),
            )
            self.authority.verify(
                plan, d, source, snapshot, close_op, self.controls.bind(close_op)
            )
            closed = browser.close(close_op, self.controls.bind(close_op))
            ending_ref = closed.events[-1].evidence[0]
            s.references.append(ending_ref)
            require_complete_read_bound(ending_ref, 64 * 1024**2)
            ending_bytes = self.reads.read(ending_ref, control)
            require_complete_bytes(ending_ref, ending_bytes)
            closure = ClosureReceipt.model_validate_json(
                json.dumps(json.loads(ending_bytes)["details"]["closure"])
            )
            s.closure_ref = self.writer.put(
                closure.model_dump_json().encode(), closure.schema_version, control
            )
            s.references.append(s.closure_ref)
            s.phase = "guard"
            prepared = self.reads.parse(
                source.prepare_request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
            if (
                prepared.action != "prepare"
                or prepared.snapshot_ref is None
                or prepared.binding_ref != plan.evaluation.task_contract_ref
                or prepared.task != d.scope.task
                or prepared.operation.allocation_id
                != self.site_spec.token.allocation_id
            ):
                raise OwnershipConflict(
                    "Original complete prepared snapshot required for guard"
                )
            guard_op = prepared.operation.model_copy(
                update={
                    "operation_id": d.guard_operation_id,
                    "parent_operation_id": closure.operation_id,
                    "deadline": plan.operation.deadline,
                    "cancellation_ref": plan.operation.cancellation_ref,
                }
            )
            self.authority.verify(
                plan, d, source, snapshot, guard_op, self.controls.bind(guard_op)
            )
            guard = RecordedSiteCapture(
                self.site.capture, self.evidence, self.site_authority
            )
            guard_ref = guard.capture(
                SiteCaptureRequest(
                    inspection=prepared.model_copy(
                        update={"action": "inspect", "operation": guard_op}
                    ),
                    collector_id=d.guard_collector_id,
                    collector_version=d.guard_collector_version,
                ),
                control=self.controls.bind(guard_op),
            )
            assert guard.intent_ref is not None
            s.references.extend((guard.intent_ref, guard_ref))
            s.selection_ref = self.records.selection(
                source,
                s.terminal_ref,
                s.closure_ref,
                guard.intent_ref,
                guard_ref,
                control,
            )
            s.references.append(s.selection_ref)
            s.result = TaskCaptureResult(
                contract=plan.evaluation, references=tuple(dict.fromkeys(s.references))
            )
            self.authority.verify(plan, d, source, snapshot, operation, control)
            control.checkpoint()
            s.phase = "captured"
            return s.result
        except BaseException as error:
            phase = s.phase
            s.phase = "quarantined"
            raise TaskCaptureUnconfirmed(error, s, self.writer, phase) from error
