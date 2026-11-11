"""Worker-local binding to its returned restore; parent must admit durable intent."""

import hashlib
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..frontend_contract import AdminFrontendStopped
from ..state_contract import AdminStateRestored
from ..instance import AdminInstance
from .product_lifecycle import AdminProductLifecycle
from .product_recovery_contract import ProductRestored


class ProductResume:
    def __init__(
        self, instance: AdminInstance, lifecycle: AdminProductLifecycle
    ) -> None:
        self.instance, self.lifecycle = instance, lifecycle
        self.attempted = False
        self.current: ProductRestored | None = None

    def verify(
        self,
        stopped: AdminFrontendStopped,
        restored: AdminStateRestored,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        original = self.current
        if original is None or (stopped, restored) != (
            original.frontend,
            original.state,
        ):
            raise PermissionError("Resume has no original delegated completed restore")
        if self.instance.spec != stopped.service or self.instance.port_lease is None:
            raise OwnershipConflict("Resume lost original instance or lease")

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        task = self.lifecycle
        if (
            self.attempted
            or task.busy
            or task.phase != "restored"
            or task.restore_result is None
            or task.restore_request != request.restore_request
        ):
            raise OwnershipConflict(
                "Resume requires original returned restore and one attempt"
            )
        raw = task.restore_result.model_dump_json().encode()
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
            request.restore_result_ref.sha256,
            request.restore_result_ref.size_bytes,
        ):
            raise OwnershipConflict(
                "Resume reference differs from original worker result"
            )
        original = ProductRestored.model_validate_json(
            task.restore_result.private_result
        )
        if original.operation != request.restore_request.operation:
            raise OwnershipConflict("Resume changed original restoration operation")
        control.checkpoint()
        self.attempted, self.current = True, original
        try:
            recovered = self.instance.recover_frontend(original.state, self, control)
            return SiteResumeResult(
                request_sha256=request.digest,
                private_result=recovered.model_dump_json(),
            )
        finally:
            self.current = None
