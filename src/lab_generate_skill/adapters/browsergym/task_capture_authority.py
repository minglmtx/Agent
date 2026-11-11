"""Passive initial/terminal capture bound to original producers and live browser."""

import hashlib
from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.trace_journal import TraceJournal


class OriginalTaskBrowserCaptureAuthority:
    def __init__(
        self,
        resources: OriginalTaskResourceOwner,
        initialization: Callable[[], RecordedTaskInitialization],
        capture: Callable[[], RecordedTaskCapture],
        trace: Callable[[], TraceJournal],
    ) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner) or any(
            not callable(v) for v in (initialization, capture, trace)
        ):
            raise TypeError("Original task and passive capture producers required")
        self.resources, self.initialization, self.capture, self.trace = (
            resources,
            initialization,
            capture,
            trace,
        )

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        r = self.resources
        request = BrowserCaptureRequest.model_validate(request)
        b = r.require_browser(request.operation, control)
        if (
            configuration != b.spec.configuration
            or request.scope != configuration.spec.scope
            or b.session.observation_ref is None
            or request.observation_sha256 != b.session.observation_ref.sha256
        ):
            raise OwnershipConflict(
                "Passive capture changed original current browser view"
            )
        intent = r.owner.reads.parse(
            intent_ref, "browser-capture-intent/1", BrowserCaptureIntent, control
        )
        if (
            intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict("Passive capture changed original persisted intent")
        initial = self.initialization()
        d = initial.declaration
        if request.operation == d.capture_operation:
            measurements = initial.measurements
            if (
                initial.state.phase != "initial"
                or initial.browser is not b
                or not isinstance(measurements, CapturedTaskInitialMeasurements)
                or measurements.plan != d
                or measurements.browser is not b
                or measurements.authority is not self
                or not measurements.attempted
                or measurements.capture is None
                or measurements.capture.intent_ref != intent_ref
                or (request.collector_id, request.collector_version)
                != (measurements.collector_id, measurements.collector_version)
            ):
                raise OwnershipConflict(
                    "Original initial capture phase/collector changed"
                )
            from lab_generate_skill.domain.observation import Observation

            observation = r.owner.reads.parse(
                b.session.observation_ref,
                "observation/1",
                Observation,
                control,
                visibility="public",
            )
            if observation.sequence != 0:
                raise OwnershipConflict("Initial capture must precede every action")
            return
        capture = self.capture()
        selected = capture.declaration
        expected = r.plan.operation.model_copy(
            update={
                "operation_id": selected.page_operation_id,
                "allocation_id": b.spec.token.allocation_id,
                "recovery_ref": b.spec.token.recovery_ref,
            }
        )
        if (
            capture.plan != r.plan
            or capture.state.phase != "page"
            or request.operation != expected
            or (request.collector_id, request.collector_version)
            != (selected.page_collector_id, selected.page_collector_version)
        ):
            raise OwnershipConflict("Original terminal capture phase/collector changed")
        snapshot = self.trace().read(r.plan.read_operation)
        sealed = snapshot.project().sealed
        if (
            snapshot.plan.binding != r.plan.intent.binding
            or sealed is None
            or sealed.final_observation_ref != b.session.observation_ref
        ):
            raise OwnershipConflict(
                "Terminal capture requires original sealed trace/current return"
            )
