"""Category source restore/resume lineage before the original full Reset."""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
    CategoryNavigationRestored,
    CategoryNavigationResumed,
)


class CategoryNavigationSourceRecoveryChecks:
    def restore(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        snapshot_ref: EvidenceRef,
        snapshot: bytes,
        control: OperationControl,
    ) -> None:
        request, result, snapshot_ref = (
            SiteTaskRequest.model_validate(request),
            SiteTaskResult.model_validate(result),
            EvidenceRef.model_validate(snapshot_ref),
        )
        control.checkpoint()
        require_complete_bytes(snapshot_ref, snapshot)
        original = CategoryNavigationRecoverySnapshot.model_validate_json(snapshot)
        restored = CategoryNavigationRestored.model_validate_json(result.private_result)
        if (
            snapshot_ref.content_schema != original.schema_version
            or snapshot_ref.visibility != "private"
            or snapshot_ref.media_type != "application/json"
            or original.model_dump_json().encode() != snapshot
            or request.action != "restore"
            or request.snapshot_ref != snapshot_ref
            or result.request_sha256 != request.digest
            or restored.request != request
            or restored.snapshot != original
            or restored.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict("Category source restore changed original lineage")
        control.checkpoint()

    def resume(
        self,
        request: SiteResumeRequest,
        result: SiteResumeResult,
        restored: SiteTaskResult,
        control: OperationControl,
    ) -> None:
        request, result, restored = (
            SiteResumeRequest.model_validate(request),
            SiteResumeResult.model_validate(result),
            SiteTaskResult.model_validate(restored),
        )
        control.checkpoint()
        raw = restored.model_dump_json().encode()
        original = CategoryNavigationRestored.model_validate_json(
            restored.private_result
        )
        resumed = CategoryNavigationResumed.model_validate_json(result.private_result)
        if (
            restored.request_sha256 != request.restore_request.digest
            or original.request != request.restore_request
            or (hashlib.sha256(raw).hexdigest(), len(raw))
            != (
                request.restore_result_ref.sha256,
                request.restore_result_ref.size_bytes,
            )
            or result.request_sha256 != request.digest
            or resumed.request != request
            or resumed.restored != original
            or resumed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict("Category source resume changed original lineage")
        control.checkpoint()
