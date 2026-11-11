"""Start the original restored native3 once and verify complete native baseline."""

import hashlib
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .image_lifecycle import ImageLifecycle
from .image_admission import task_input
from .image_recovery import ImageRestored, ImageResumed


class ImageResume:
    def __init__(self, lifecycle: ImageLifecycle) -> None:
        self.lifecycle = lifecycle
        self.attempted = False
        self.result: SiteResumeResult | None = None

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        task = self.lifecycle
        task.check_owner()
        if (
            self.attempted
            or task.busy
            or task.phase != "restored"
            or task.restore_result is None
            or task.restore_request != request.restore_request
            or request.operation.operation_id in task.operations
        ):
            raise OwnershipConflict(
                "Reddit resume requires original returned restore and one call"
            )
        raw = task.restore_result.model_dump_json().encode()
        ref = request.restore_result_ref
        if (ref.sha256, ref.size_bytes) != (hashlib.sha256(raw).hexdigest(), len(raw)):
            raise OwnershipConflict("Reddit resume changed original restoration bytes")
        restored = ImageRestored.model_validate_json(task.restore_result.private_result)
        control.checkpoint()
        self.attempted = True
        task.operations.add(request.operation.operation_id)
        task.busy = True
        task.phase = "resuming"
        try:
            endpoint = task.instance.resume(control)
            if endpoint != restored.snapshot.native_before.context.instance.endpoint:
                raise OwnershipConflict("Reddit resume changed original endpoint")
            inspection = request.restore_request.model_copy(
                update={"operation": request.operation}
            )
            measured, native = task.capture_native(
                inspection, task_input(inspection), control
            )
            task.require_pristine(measured)
            payload = ImageResumed(
                request=request,
                restored=restored,
                native=native,
                original_pins=task.instance.generations[-1].pins,
            ).model_dump_json()
            self.result = SiteResumeResult(
                request_sha256=request.digest, private_result=payload
            )
            task.phase = "resumed"
            control.checkpoint()
            return self.result
        except BaseException as error:
            task.phase = "quarantined"
            task.retain_failure(error)
            setattr(error, "reddit_resume_result", self.result)
            raise
        finally:
            task.busy = False
