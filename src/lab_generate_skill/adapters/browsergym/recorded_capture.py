"""One durable collector intent and one result, with no unknown replay."""

import hashlib
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_capture import BrowserCaptureResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.domain.errors import EvidenceIntegrityError, InvalidTransition
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.browser_capture import (
    ParentBrowserCapture,
    BrowserCaptureAuthority,
)


class RecordedBrowserCapture:
    """A single capture, not a resumable source claim or permission factory."""

    def __init__(
        self,
        client: ParentBrowserCapture,
        store: EvidenceStore,
        authority: BrowserCaptureAuthority,
    ) -> None:
        self.client, self.store, self.authority = client, store, authority
        self.attempted = False
        self.intent_ref: EvidenceRef | None = None
        self.result: BrowserCaptureResult | None = None
        self.result_ref: EvidenceRef | None = None
        self.writer = CaptureEvidence(store, "browser-capture-v1")
        self.candidates = self.writer.candidates

    def capture(
        self, request: BrowserCaptureRequest, *, control: OperationControl
    ) -> EvidenceRef:
        if self.attempted:
            raise InvalidTransition(
                "Capture already attempted; inspect original evidence only"
            )
        request = BrowserCaptureRequest.model_validate(request)
        control.checkpoint()
        intent = BrowserCaptureIntent(
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
            self.result = self.client.capture_page(
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
