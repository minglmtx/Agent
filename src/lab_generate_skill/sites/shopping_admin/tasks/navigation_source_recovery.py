"""Source restore lineage before original resume, then original full Reset checks.

Database/artifact/cache/search qualifications remain NavigationStateChecks;
no recovery action or source permission is implemented here.
"""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.ports.lifecycle import OperationControl
from ..frontend_recovery_contract import AdminFrontendRecovered
from .navigation_recovery_contract import NavigationRecoverySnapshot, NavigationRestored


class NavigationSourceRecoveryChecks:
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
        original = NavigationRecoverySnapshot.model_validate_json(snapshot)
        restored = NavigationRestored.model_validate_json(result.private_result)
        if (
            request.action != "restore"
            or request.snapshot_ref != snapshot_ref
            or result.request_sha256 != request.digest
            or (restored.task, restored.operation, restored.snapshot_ref)
            != (request.task, request.operation, snapshot_ref)
            or original.request.task != request.task
            or original.request.binding_ref != request.binding_ref
            or original.request.private_input != request.private_input
            or restored.state.snapshot_sha256 != original.state.digest
        ):
            raise OwnershipConflict(
                "Admin source restore changed original task/snapshot/result lineage"
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
        original = NavigationRestored.model_validate_json(restored.private_result)
        recovered = AdminFrontendRecovered.model_validate_json(result.private_result)
        if (
            restored.request_sha256 != request.restore_request.digest
            or (
                hashlib.sha256(restored.model_dump_json().encode()).hexdigest(),
                len(restored.model_dump_json().encode()),
            )
            != (
                request.restore_result_ref.sha256,
                request.restore_result_ref.size_bytes,
            )
            or original.operation != request.restore_request.operation
            or result.request_sha256 != request.digest
            or recovered.stopped != original.frontend
            or recovered.state_restored_sha256
            != hashlib.sha256(original.state.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Admin source resume changed original completed restore/frontends"
            )
        control.checkpoint()
