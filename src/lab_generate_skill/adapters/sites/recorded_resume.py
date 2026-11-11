"""Persist exact intent before dispatch; returned/unknown results never resend.

The original worker is once-only, remains guarded by its original controller and
cannot reconstruct completed restore from caller bytes. This wrapper does not
provide controller takeover, a replacement instance or implicit permission.
"""

import hashlib
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, InvalidTransition
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_resume import ParentSiteResume, SiteResumeAuthority


class RecordedSiteResume:
    def __init__(
        self,
        client: ParentSiteResume,
        store: EvidenceStore,
        authority: SiteResumeAuthority,
    ) -> None:
        self.client, self.store, self.authority = client, store, authority
        self.attempted = False
        self.intent_ref: EvidenceRef | None = None
        self.result: SiteResumeResult | None = None
        self.result_ref: EvidenceRef | None = None

    def _put(self, data: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="site-resume-v1",
        )
        candidate = evidence_reference(data, metadata)
        try:
            ref = EvidenceRef.model_validate(
                self.store.put(data, metadata, control=control)
            )
        except BaseException as error:
            setattr(error, "resume_candidate_reference", candidate)
            raise
        if ref.model_dump(exclude={"uri"}) != candidate.model_dump(exclude={"uri"}):
            mismatch = EvidenceIntegrityError(
                "Resume publication changed actual bytes or metadata"
            )
            setattr(mismatch, "resume_candidate_reference", ref)
            raise mismatch
        return ref

    def resume(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> EvidenceRef:
        if self.attempted:
            raise InvalidTransition(
                "Resume publication or dispatch already attempted; inspect original only"
            )
        request = SiteResumeRequest.model_validate(request)
        request.check_site(self.client.configuration)
        control.checkpoint()
        raw = self.store.read(request.restore_result_ref, control=control)
        restored = SiteTaskResult.model_validate_json(raw)
        if (
            restored.model_dump_json().encode() != raw
            or restored.request_sha256 != request.restore_request.digest
        ):
            raise EvidenceIntegrityError(
                "Resume requires actual canonical original restore result"
            )
        intent = SiteResumeIntent(
            configuration_sha256=hashlib.sha256(
                self.client.configuration.model_dump_json().encode()
            ).hexdigest(),
            request=request,
        )
        self.attempted = True
        try:
            self.intent_ref = self._put(
                intent.model_dump_json().encode(), intent.schema_version, control
            )
            control.checkpoint()
            self.result = self.client.resume_frontend(
                request, self.intent_ref, self.authority, control=control
            )
            if self.result.request_sha256 != request.digest:
                raise EvidenceIntegrityError("Resume returned another request result")
            self.result_ref = self._put(
                self.result.model_dump_json().encode(),
                self.result.schema_version,
                control,
            )
            control.checkpoint()
            return self.result_ref
        except BaseException as error:
            setattr(error, "resume_intent_reference", self.intent_ref)
            setattr(error, "resume_returned_result", self.result)
            setattr(error, "resume_result_reference", self.result_ref)
            raise
