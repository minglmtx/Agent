"""One original Group native initial capture under current starting authority."""

import hashlib
import os
import threading
from collections.abc import Callable
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_held_site import original_acquired_task_site
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.evidence_schema import GitlabSiteCapture
from lab_generate_skill.sites.gitlab.tasks.group_initial_capture import (
    group_initial_capture_request,
)


class GroupInitialNativeCapture:
    def __init__(
        self,
        preparation: RecordedSiteTaskPreparation,
        initialization: Callable[[], RecordedTaskInitialization],
    ) -> None:
        if not isinstance(preparation, RecordedSiteTaskPreparation) or not callable(
            initialization
        ):
            raise TypeError("Original Group task producers required")
        self.preparation, self.initialization = preparation, initialization
        self.owner = os.getpid(), threading.get_ident()
        self.recorder: RecordedSiteCapture | None = None
        self.request: SiteCaptureRequest | None = None
        self.attempted = self.consumed = False

    def record(self, control: OperationControl) -> GitlabSiteCapture:
        if self.attempted:
            raise DispatchAlreadyCommitted(
                "Original Group initial native capture already attempted"
            )
        control.checkpoint()
        current, p = self.initialization(), self.preparation
        prepared = p.state.prepare_request
        if prepared is None or current.state.phase != "initial":
            raise OwnershipConflict("Original Group prepared starting phase required")
        self.request = group_initial_capture_request(current.declaration, prepared)
        self.attempted = True
        self.recorder = RecordedSiteCapture(p.site.capture, current.evidence, self)
        try:
            result = self.recorder.capture(
                self.request, control=current.controls.bind(self.request.operation)
            )
            assert self.recorder.intent_ref is not None
            return GitlabSiteCapture(
                intent_ref=self.recorder.intent_ref, result_ref=result
            )
        except BaseException as error:
            setattr(error, "group_initial_native_return", self.recorder.result)
            raise
        finally:
            # Retain both confirmed references and unconfirmed write candidates
            # on the existing initialization state even when record() raises.
            for ref in (self.recorder.intent_ref, self.recorder.result_ref):
                if ref is not None:
                    current.state.references.append(ref)
            current.state.candidates.extend(self.recorder.candidates)

    def pair(self) -> GitlabSiteCapture:
        recorder = self.recorder
        if (
            recorder is None
            or recorder.intent_ref is None
            or recorder.result_ref is None
        ):
            raise OwnershipConflict(
                "Confirmed original Group native before capture required"
            )
        return GitlabSiteCapture(
            intent_ref=recorder.intent_ref, result_ref=recorder.result_ref
        )

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.owner != (os.getpid(), threading.get_ident()) or self.consumed:
            raise OwnershipConflict(
                "Group native initial capture changed owner or repeated permission"
            )
        current, p = self.initialization(), self.preparation
        measurements = current.measurements
        if not isinstance(measurements, CapturedTaskInitialMeasurements):
            raise TypeError(
                "Original Group initial browser measurement producer required"
            )
        page = measurements.capture
        state = current.state
        if (
            current.plan != p.plan
            or current.preparations is not p.records
            or state.phase != "initial"
            or state.selection is None
            or current.browser.phase != "open"
            or configuration != p.spec.configuration
            or p.state.phase != "prepared"
            or p.state.prepare_request is None
            or current.declaration.prepared_result_ref != p.state.result_ref
            or page is None
            or page.intent_ref is None
            or page.result_ref is None
            or request != self.request
            or request
            != group_initial_capture_request(
                current.declaration, p.state.prepare_request
            )
        ):
            raise OwnershipConflict(
                "Original Group unique initial producer and native request required"
            )
        reads = StateReads(current.evidence)
        frozen = reads.read(current.declaration_ref, control)
        if frozen != current.declaration.model_dump_json().encode():
            raise OwnershipConflict(
                "Group initialization declaration changed before native capture"
            )
        original = current.initials.load(state.selection, request.operation, control)
        session = current.browser.session
        if (
            session.last_return_ref
            != original.acquired.details.started.initial_return_ref
            or session.observation_ref
            != original.acquired.details.started.initial_observation_ref
            or original.observation.record.sequence != 0
        ):
            raise OwnershipConflict(
                "Group native before capture cannot follow an Actor action"
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
            raise OwnershipConflict(
                "Original Group native capture intent producer required"
            )
        intent = reads.parse(
            intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
        )
        if (
            intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Original Group persisted native capture intent changed"
            )
        current.authority.verify(
            current.plan, current.declaration, request.operation, control
        )
        original_acquired_task_site(p, request.operation, control)
        control.checkpoint()
        self.consumed = True
