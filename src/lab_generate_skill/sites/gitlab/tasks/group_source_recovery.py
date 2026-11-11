"""Original Group source restore/resume lineage on the shared recovery port."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.ports.lifecycle import OperationControl
from .group_recovery import GroupRecoverySnapshot, GroupRestored, GroupResumed


class GroupSourceRecoveryChecks:
    def restore(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        snapshot_ref: EvidenceRef,
        snapshot: bytes,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        request, result, snapshot_ref = (
            SiteTaskRequest.model_validate(request),
            SiteTaskResult.model_validate(result),
            EvidenceRef.model_validate(snapshot_ref),
        )
        original = GroupRecoverySnapshot.model_validate_json(snapshot)
        restored = GroupRestored.model_validate_json(result.private_result)
        if (
            request.action != "restore"
            or request.snapshot_ref != snapshot_ref
            or result.request_sha256 != request.digest
            or restored.request != request
            or restored.snapshot != original
            or hashlib.sha256(snapshot).hexdigest() != snapshot_ref.sha256
            or len(snapshot) != snapshot_ref.size_bytes
            or original.model_dump_json().encode() != snapshot
            or restored.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Group source restore changed original complete snapshot/request"
            )
        control.checkpoint()

    def resume(
        self,
        request: SiteResumeRequest,
        result: SiteResumeResult,
        restored: SiteTaskResult,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        request, result, restored = (
            SiteResumeRequest.model_validate(request),
            SiteResumeResult.model_validate(result),
            SiteTaskResult.model_validate(restored),
        )
        original = GroupRestored.model_validate_json(restored.private_result)
        resumed = GroupResumed.model_validate_json(result.private_result)
        raw = restored.model_dump_json().encode()
        if (
            restored.request_sha256 != request.restore_request.digest
            or (hashlib.sha256(raw).hexdigest(), len(raw))
            != (
                request.restore_result_ref.sha256,
                request.restore_result_ref.size_bytes,
            )
            or original.request != request.restore_request
            or result.request_sha256 != request.digest
            or resumed.request != request
            or resumed.restored != original
            or resumed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Group source resume changed original completed restore/generation"
            )
        control.checkpoint()
