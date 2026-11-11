"""Existing resume request bound to original unchanged Map frontend recovery."""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_lifecycle import MapTaskLifecycle


class MapTaskResume:
    def __init__(self, lifecycle: MapTaskLifecycle) -> None:
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
                "Map resume requires original returned restore and one call"
            )
        raw = task.restore_result.model_dump_json().encode()
        ref = request.restore_result_ref
        if (ref.sha256, ref.size_bytes) != (hashlib.sha256(raw).hexdigest(), len(raw)):
            raise OwnershipConflict("Map resume changed original restoration bytes")
        restored = task.codecs.read_restored(task.restore_result.private_result)
        control.checkpoint()
        self.attempted = True
        task.operations.add(request.operation.operation_id)
        task.busy = True
        task.phase = "resuming"
        try:
            resumed = task.reset.resume(control)
            # Preserve original restore task/recovery; this linked cleanup call
            # has its own ID and state artifact. It is not a replay of restore.
            inspection = SiteTaskRequest.model_validate(
                {**request.restore_request.model_dump(), "operation": request.operation}
            )
            native = task.capture_state(inspection, control)
            payload = task.codecs.resumed(
                request, restored, resumed, native
            ).model_dump_json()
            self.result = SiteResumeResult(
                request_sha256=request.digest, private_result=payload
            )
            task.phase = "resumed"
            control.checkpoint()
            return self.result
        except BaseException as error:
            task.phase, task.error = "quarantined", error
            task.retain_failure(error)
            setattr(error, "map_resume_result", self.result)
            raise
        finally:
            task.busy = False
