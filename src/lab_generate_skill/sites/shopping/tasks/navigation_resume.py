"""One original category restoration resume with complete native remeasurement."""

import hashlib
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_lifecycle import CategoryNavigationLifecycle
from .navigation_recovery import CategoryNavigationRestored, CategoryNavigationResumed


class CategoryNavigationResume:
    def __init__(self, lifecycle: CategoryNavigationLifecycle) -> None:
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
                "Category resume requires original returned restore and one call"
            )
        raw, ref = (
            task.restore_result.model_dump_json().encode(),
            request.restore_result_ref,
        )
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (ref.sha256, ref.size_bytes):
            raise OwnershipConflict(
                "Category resume changed original restoration bytes"
            )
        restored = CategoryNavigationRestored.model_validate_json(
            task.restore_result.private_result
        )
        control.checkpoint()
        self.attempted = True
        instance = task.instance
        instance.resume(control)
        payload = CategoryNavigationResumed(
            request=request,
            restored=restored,
            protected=task.native.protected(control),
            original_pins=instance.generations[-1].pins,
        ).model_dump_json()
        self.result = SiteResumeResult(
            request_sha256=request.digest, private_result=payload
        )
        control.checkpoint()
        return self.result
