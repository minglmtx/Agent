"""Original source restore/browser closure/intent before the fixed resume port."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
    PendingQualificationNative,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class PendingQualificationResume:
    request: SiteResumeRequest
    restore: PendingQualificationNative
    restore_result: SiteTaskResult
    restore_result_ref: EvidenceRef


class SourceQualificationResumeAuthority:
    def __init__(
        self,
        native: SourceQualificationNativeAuthority,
        pending: Callable[[], PendingQualificationResume | None],
    ) -> None:
        if not isinstance(native, SourceQualificationNativeAuthority) or not callable(
            pending
        ):
            raise TypeError(
                "Original source/native and completed restore producer required"
            )
        self.native, self.pending = native, pending
        self.consumed = False

    def verify_resume(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        self.native.owner.require(request.operation, control, new_work=False)
        self.native.require_acquired(request.operation, control)
        if self.consumed:
            raise DispatchAlreadyCommitted(
                "Original source resume permission already consumed"
            )
        known = self.pending()
        if not isinstance(known, PendingQualificationResume):
            raise OwnershipConflict(
                "Original source resume is not awaiting its own dispatch"
            )
        request = SiteResumeRequest.model_validate(request)
        request.check_site(configuration)
        self.native.require_closed_browser(known.restore, control)
        read = self.native.reads
        intent = read.parse(
            intent_ref, "site-resume-intent/1", SiteResumeIntent, control
        )
        if (
            configuration != self.native.spec.configuration
            or request != known.request
            or request.restore_request != known.restore.request
            or request.restore_result_ref != known.restore_result_ref
            or known.restore_result.request_sha256 != known.restore.request.digest
            or read.parse(
                known.restore_result_ref, "site-task-result/1", SiteTaskResult, control
            )
            != known.restore_result
            or intent_ref.producer != "site-resume-v1"
            or intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Source resume changed original restore/result/intent bytes"
            )
        self.native.owner.require(request.operation, control, new_work=False)
        self.consumed = True
