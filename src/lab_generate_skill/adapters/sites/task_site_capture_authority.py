"""Current producer-bound native guard permission on the original capture port.

No independent business grant: the existing task capture authority rechecks its
original source/claim/run/physical gates. This adapter binds that permission to
one actual fixed-worker intent and the original acquired site/closed browser.
"""

import hashlib
import os
import threading
from collections.abc import Callable
from lab_generate_skill.adapters.browsergym.retained_closure import (
    original_closed_browser,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_capture import RecordedTaskCapture
from .task_preparation import RecordedSiteTaskPreparation
from .task_held_site import original_acquired_task_site


class OriginalTaskSiteCaptureAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        preparation: RecordedSiteTaskPreparation,
        capture: Callable[[], RecordedTaskCapture],
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if (
            preparation is None
            or not callable(capture)
            or preparation.plan != self.plan
        ):
            raise ValueError("Original current task producers required")
        self.preparation, self.capture = preparation, capture
        self.owner = os.getpid(), threading.get_ident()
        self.consumed = False

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Capture authority changed original owner")
        if self.consumed:
            raise DispatchAlreadyCommitted(
                "Original native guard permission already consumed"
            )
        request = SiteCaptureRequest.model_validate(request)
        c, p = self.capture(), self.preparation
        d, state = c.declaration, c.state
        if (
            c.plan != self.plan
            or c.site_spec != p.spec
            or configuration != p.spec.configuration
            or state.phase != "guard"
            or state.inputs is None
            or state.closure_ref is None
            or p.state.prepare_request is None
            or state.inputs.prepare_request_ref != p.state.prepare_request_ref
            or (request.collector_id, request.collector_version)
            != (d.guard_collector_id, d.guard_collector_version)
            or request.selection_ref is not None
        ):
            raise OwnershipConflict("Only original current guard phase is authorized")
        closure = c.reads.parse(
            state.closure_ref, "closure-receipt/1", ClosureReceipt, control
        )
        prepared = p.state.prepare_request
        operation = prepared.operation.model_copy(
            update={
                "operation_id": d.guard_operation_id,
                "parent_operation_id": closure.operation_id,
                "deadline": self.plan.operation.deadline,
                "cancellation_ref": self.plan.operation.cancellation_ref,
            }
        )
        expected = prepared.model_copy(
            update={"action": "inspect", "operation": operation}
        )
        if (
            request.inspection != expected
            or request.inspection.snapshot_ref != p.state.snapshot_ref
        ):
            raise OwnershipConflict(
                "Native guard changed original prepared snapshot or operation"
            )
        if (
            intent_ref.content_schema,
            intent_ref.visibility,
            intent_ref.media_type,
            intent_ref.producer,
        ) != (
            "site-capture-intent/2",
            "private",
            "application/json",
            "site-capture-v1",
        ):
            raise OwnershipConflict("Original native guard intent producer required")
        intent = c.reads.parse(
            intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
        )
        if (
            intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict("Native guard changed original persisted intent")
        snapshots = [
            r
            for r in state.references
            if r.content_schema == "trace-journal-snapshot/1"
        ]
        if len(snapshots) != 1:
            raise OwnershipConflict("Original single sealed trace required")
        snapshot = c.reads.parse(
            snapshots[0], "trace-journal-snapshot/1", TraceSnapshot, control
        )
        c.authority.verify(self.plan, d, state.inputs, snapshot, operation, control)
        browser = c.browser()
        read = operation.model_copy(
            update={
                "operation_id": operation.operation_id + ".closed-read",
                "mode": "cleanup",
                "allocation_id": browser.spec.token.allocation_id,
                "recovery_ref": browser.spec.token.recovery_ref,
                "cancellation_ref": None,
                "parent_operation_id": browser.operation.operation_id,
            }
        )
        ending = original_closed_browser(
            browser.spec, browser.operation, read, browser.journal, c.evidence, control
        )
        if (
            closure.token != browser.spec.token
            or closure.status != "closed"
            or ending.events[-1].evidence[0] not in state.references
        ):
            raise OwnershipConflict(
                "Native guard requires the original full browser closure"
            )
        original_acquired_task_site(p, operation, control)
        control.checkpoint()
        self.consumed = True
