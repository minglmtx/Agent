"""Original passive capture and existing initial-record producer, once only."""

from collections.abc import Callable
import hashlib
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.initial_observation import BrowserAcquiredFact
from lab_generate_skill.domain.browser_initialization import PublicNavigation
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation_publication import (
    PublishedInitialObservation,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .retained_resource import RetainedBrowserResource
from .worker_client import SupervisedBrowserSession
from .recorded_capture import RecordedBrowserCapture


class CapturedTaskInitialMeasurements:
    def __init__(
        self,
        plan: TaskInitializationPlan,
        browser: RetainedBrowserResource,
        store: EvidenceStore,
        controls: OperationControls,
        authority: BrowserCaptureAuthority,
        records: Callable[[EvidenceRef, EvidenceRef], EvidenceInitialObservations],
        *,
        collector_id: str,
        collector_version: str,
    ) -> None:
        if any(x is None for x in (browser, store, controls, authority, records)):
            raise ValueError("Original initial capture/records/authority are mandatory")
        self.plan, self.browser, self.store, self.controls = (
            TaskInitializationPlan.model_validate(plan),
            browser,
            store,
            controls,
        )
        self.authority, self.records_factory = authority, records
        self.collector_id, self.collector_version = collector_id, collector_version
        self.attempted = False
        self.capture: RecordedBrowserCapture | None = None
        self.initial_ref: EvidenceRef | None = None

    def record(
        self, selection: InitialObservationSelection, control: OperationControl
    ) -> EvidenceRef:
        return self.record_complete(selection, control).reference

    def record_complete(
        self, selection: InitialObservationSelection, control: OperationControl
    ) -> PublishedInitialObservation:
        if self.attempted:
            raise DispatchAlreadyCommitted(
                "Original initial measurement already attempted"
            )
        control.checkpoint()
        session = self.browser.session
        client = session.engine
        if (
            not isinstance(client, SupervisedBrowserSession)
            or session.observation_ref is None
            or selection.browser_acquired_ref != session.resource_started_ref
            or selection.browser_spec_ref != self.plan.browser_spec_ref
            or client.configuration != self.browser.spec.configuration
            or self.browser.spec.configuration.spec.scope != self.plan.scope
            or self.browser.operation != self.plan.browser_acquisition
        ):
            raise OwnershipConflict(
                "Initial capture changed original registered first return"
            )
        selected = self.browser.spec.configuration.initialization
        if (
            isinstance(selected, PublicNavigation)
            or selected.prepared_ref != selection.preparation.prepared_ref
        ):
            raise OwnershipConflict("Initial capture changed original preparation")
        assert session.resource_started_ref is not None
        raw = self.store.read(session.resource_started_ref, control=control)
        require_complete_bytes(session.resource_started_ref, raw)
        acquired = BrowserAcquiredFact.model_validate_json(raw)
        if (
            acquired.token != self.browser.spec.token
            or acquired.spec_sha256
            != hashlib.sha256(self.browser.spec.model_dump_json().encode()).hexdigest()
            or acquired.details.started.initial_observation_ref
            != session.observation_ref
            or acquired.details.started.initial_return_ref != session.last_return_ref
        ):
            raise OwnershipConflict(
                "Initial measurement cannot follow an action/stale first return"
            )
        request = BrowserCaptureRequest(
            scope=self.plan.scope,
            operation=self.plan.capture_operation,
            observation_sha256=session.observation_ref.sha256,
            collector_id=self.collector_id,
            collector_version=self.collector_version,
        )
        self.attempted = True
        self.capture = RecordedBrowserCapture(client, self.store, self.authority)
        try:
            result_ref = self.capture.capture(
                request, control=self.controls.bind(request.operation)
            )
            if self.capture.intent_ref is None:
                raise OwnershipConflict(
                    "Original initial capture intent was not confirmed"
                )
            records = self.records_factory(self.capture.intent_ref, result_ref)
            complete = records.publish_complete(selection, self.plan.initial_operation)
            self.initial_ref = complete.reference
            control.checkpoint()
            return complete
        except BaseException as error:
            setattr(error, "capture_intent_reference", self.capture.intent_ref)
            setattr(error, "capture_returned_result", self.capture.result)
            setattr(error, "capture_result_reference", self.capture.result_ref)
            setattr(
                error, "capture_candidate_references", tuple(self.capture.candidates)
            )
            setattr(error, "initial_checks_reference", self.initial_ref)
            raise
