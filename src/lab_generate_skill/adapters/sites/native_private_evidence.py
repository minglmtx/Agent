"""Complete private JSON via existing CAS; small original-request descriptor.

Transport only: this does not validate site semantics or grant task execution.
Trusted bootstrap supplies the controlled EvidenceStore and mandatory admission;
there is no filesystem fallback, chunking, wire-limit increase or Actor tool.
"""

import hashlib
import os
import threading
from typing import Literal
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_private_fact import (
    SitePrivateEvidenceContext,
    SitePrivateEvidenceResult,
)
from lab_generate_skill.ports.site_evidence import SitePrivateEvidenceAdmission
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object

from lab_generate_skill.domain.native_private_json import NativePrivateJsonProfile


def check_native_payload(
    reference: EvidenceRef,
    plan: SitePrivateEvidencePlan,
    profile: NativePrivateJsonProfile,
) -> None:
    plan = SitePrivateEvidencePlan.model_validate(plan)
    profile = NativePrivateJsonProfile.model_validate(profile)
    if plan.profile != profile:
        raise EvidenceIntegrityError("Native payload changed declared private profile")
    reference = EvidenceRef.model_validate_json(
        EvidenceRef.model_validate(reference).model_dump_json()
    )
    if (
        (
            reference.visibility,
            reference.media_type,
            reference.content_schema,
            reference.producer,
        )
        != ("private", "application/json", profile.content_schema, profile.producer)
        or reference.uri != f"cas://sha256/{reference.sha256}"
        or not 0
        < reference.size_bytes
        <= min(plan.config.max_object_bytes, MAX_OBJECT_BYTES)
    ):
        raise EvidenceIntegrityError("Complete private native JSON reference required")


class NativePrivateEvidence:
    def __init__(
        self,
        plan: SitePrivateEvidencePlan,
        context: SitePrivateEvidenceContext,
        evidence: EvidenceStore,
        admission: SitePrivateEvidenceAdmission,
        *,
        profile: NativePrivateJsonProfile,
    ) -> None:
        self.plan = SitePrivateEvidencePlan.model_validate(plan)
        self.context = SitePrivateEvidenceContext.model_validate_json(
            context.model_dump_json()
        )
        self.profile = NativePrivateJsonProfile.model_validate_json(
            profile.model_dump_json()
        )
        if (
            self.context.site_id != self.profile.site_id
            or self.plan.profile != self.profile
        ):
            raise OwnershipConflict("Native transport profile changed original site")
        self.plan.check_site(
            self.context.token,
            self.context.instance.files,
            self.plan.config.installation,
        )
        self.evidence, self.admission = evidence, admission
        self.owner = (os.getpid(), threading.get_ident())
        self.attempted: set[str] = set()
        self.quarantined = False
        self.last_candidate: SitePrivateEvidenceResult | None = None

    def _check(
        self,
        request: SiteTaskRequest,
        phase: Literal["publish", "read"],
        control: OperationControl,
    ) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Private evidence changed original owner process/thread"
            )
        control.checkpoint()
        token_owner = self.plan.binding.owner
        if (
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.allocation_id,
        ) != (
            token_owner.run_id,
            token_owner.owner_id,
            self.context.token.allocation_id,
        ) or (
            request.task.site,
            request.task.family,
            request.task.contract_version,
            request.task.split,
        ) != (
            self.profile.site_id,
            self.profile.family,
            1,
            "train",
        ):
            raise OwnershipConflict("Private evidence changed original run or site")
        self.admission.authorize(self.plan, self.context, request, phase, control)

    def publish(
        self, request: SiteTaskRequest, raw: bytes, *, control: OperationControl
    ) -> SitePrivateEvidenceResult:
        request = SiteTaskRequest.model_validate_json(
            SiteTaskRequest.model_validate(request).model_dump_json()
        )
        if self.quarantined or request.operation.operation_id in self.attempted:
            raise InvalidTransition(
                "Private native publication cannot repeat an attempted operation"
            )
        if type(raw) is not bytes or not 0 < len(raw) <= min(
            self.plan.config.max_object_bytes, MAX_OBJECT_BYTES
        ):
            raise ValueError(
                "Complete native JSON exceeds the declared private CAS limit"
            )
        json_object(raw)
        self._check(request, "publish", control)
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=self.profile.content_schema,
            visibility="private",
            producer=self.profile.producer,
        )
        expected = evidence_reference(raw, metadata)
        candidate = SitePrivateEvidenceResult(
            request_sha256=request.digest, context=self.context, payload_ref=expected
        )
        # Reserve before the first potentially effectful put. Neither a lost
        # confirmation nor an expired caller permits SQL/action/publication replay.
        self.attempted.add(request.operation.operation_id)
        self.last_candidate = candidate
        self.quarantined = True
        actual = self.evidence.put(raw, metadata, control=control)
        if actual != expected:
            raise EvidenceIntegrityError(
                "Private CAS changed complete native object identity"
            )
        control.checkpoint()
        self.quarantined = False
        return candidate

    def read(
        self,
        request: SiteTaskRequest,
        result: SitePrivateEvidenceResult,
        *,
        control: OperationControl,
    ) -> bytes:
        if self.quarantined:
            raise InvalidTransition(
                "Unknown publication requires original storage resolution before reuse"
            )
        request = SiteTaskRequest.model_validate_json(
            SiteTaskRequest.model_validate(request).model_dump_json()
        )
        result = SitePrivateEvidenceResult.model_validate_json(
            SitePrivateEvidenceResult.model_validate(result).model_dump_json()
        )
        if result.request_sha256 != request.digest or result.context != self.context:
            raise OwnershipConflict(
                "Private native evidence differs from original request/worker/instance"
            )
        check_native_payload(result.payload_ref, self.plan, self.profile)
        self._check(request, "read", control)
        raw = self.evidence.read(result.payload_ref, control=control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            result.payload_ref.size_bytes,
            result.payload_ref.sha256,
        ):
            raise EvidenceIntegrityError(
                "Complete private native bytes differ from the reference"
            )
        json_object(raw)
        control.checkpoint()
        return raw
