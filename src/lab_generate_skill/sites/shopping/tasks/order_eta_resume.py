"""Resume only the original returned restoration, then remeasure native state."""

import hashlib
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .order_eta_lifecycle import OrderEtaLifecycle
from .order_eta_recovery import OrderEtaRestored, OrderEtaResumed


class OrderEtaResume:
    def __init__(self, lifecycle: OrderEtaLifecycle) -> None:
        self.lifecycle = lifecycle
        self.attempted = False
        self.result: SiteResumeResult | None = None

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
                "Shopping resume requires original returned restore and one call"
            )
        raw = task.restore_result.model_dump_json().encode()
        ref = request.restore_result_ref
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (ref.sha256, ref.size_bytes):
            raise OwnershipConflict(
                "Shopping resume changed original restoration bytes"
            )
        restored = OrderEtaRestored.model_validate_json(
            task.restore_result.private_result
        )
        control.checkpoint()
        self.attempted = True
        instance = task.instance
        instance.resume(control)
        observed = task.native.protected(control)
        payload = OrderEtaResumed(
            request=request,
            restored=restored,
            protected=observed,
            original_pins=instance.generations[-1].pins,
        ).model_dump_json()
        self.result = SiteResumeResult(
            request_sha256=request.digest, private_result=payload
        )
        control.checkpoint()
        return self.result
