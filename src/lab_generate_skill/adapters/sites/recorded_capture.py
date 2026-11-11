"""One durable collector intent and one result, with no unknown replay."""

import hashlib
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.domain.errors import EvidenceIntegrityError, InvalidTransition
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_capture import (
    ParentSiteCapture,
    SiteCaptureAuthority,
)


class RecordedSiteCapture:
    """A single capture, not a resumable source claim or permission factory."""

    def __init__(
        self,
        client: ParentSiteCapture,
        store: EvidenceStore,
        authority: SiteCaptureAuthority,
    ) -> None:
        self.client, self.store, self.authority = client, store, authority
        self.attempted = False
        self.intent_ref: EvidenceRef | None = None
        self.result: SiteTaskResult | None = None
        self.result_ref: EvidenceRef | None = None
        self.writer = CaptureEvidence(store, "site-capture-v1")
        self.candidates = self.writer.candidates

    def capture(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> EvidenceRef:
        if self.attempted:
            raise InvalidTransition(
                "Capture already attempted; inspect original evidence only"
            )
        request = SiteCaptureRequest.model_validate(request)
        request.check_site(self.client.configuration)
        control.checkpoint()
        intent = SiteCaptureIntent(
            configuration_sha256=hashlib.sha256(
                self.client.configuration.model_dump_json().encode()
            ).hexdigest(),
            request=request,
        )
        self.attempted = True
        try:
            self.intent_ref = self.writer.put(
                intent.model_dump_json().encode(), intent.schema_version, control
            )
            self.result = self.client.capture_task(
                request, self.intent_ref, self.authority, control=control
            )
            if self.result.request_sha256 != request.digest:
                raise EvidenceIntegrityError("Capture returned another request result")
            self.result_ref = self.writer.put(
                self.result.model_dump_json().encode(),
                self.result.schema_version,
                control,
            )
            return self.result_ref
        except BaseException as error:
            setattr(error, "capture_intent_reference", self.intent_ref)
            setattr(error, "capture_returned_result", self.result)
            setattr(error, "capture_result_reference", self.result_ref)
            setattr(error, "capture_candidate_references", tuple(self.candidates))
            raise
