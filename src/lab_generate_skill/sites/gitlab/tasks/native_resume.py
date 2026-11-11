"""Once-only confirmation of the original restored GitLab generation."""

from collections.abc import Callable
import hashlib
from typing import Generic, TypeVar
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_lifecycle import GitlabNativeLifecycle, Spec, State, Snapshot

Restored = TypeVar("Restored")


class GitlabNativeResume(Generic[Spec, State, Snapshot, Restored]):
    def __init__(
        self,
        lifecycle: GitlabNativeLifecycle[Spec, State, Snapshot],
        decode: Callable[[str], Restored],
        resumed: Callable[
            [
                SiteResumeRequest,
                Restored,
                SitePrivateEvidenceResult,
                tuple[NativeNamespaceIdentity, ...],
            ],
            str,
        ],
    ) -> None:
        self.lifecycle, self.decode, self.make_resumed = lifecycle, decode, resumed
        self.attempted = False

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        task = self.lifecycle
        task.check_owner()
        if (
            self.attempted
            or task.resume_attempted
            or task.busy
            or task.phase != "restored"
            or task.restore_result is None
            or task.restore_request != request.restore_request
        ):
            raise OwnershipConflict(
                task.label + " resume requires original returned restore and one call"
            )
        raw, ref = (
            task.restore_result.model_dump_json().encode(),
            request.restore_result_ref,
        )
        if (ref.sha256, ref.size_bytes) != (hashlib.sha256(raw).hexdigest(), len(raw)):
            raise OwnershipConflict(
                task.label + " resume changed original restore bytes"
            )
        restored = self.decode(task.restore_result.private_result)
        control.checkpoint()
        self.attempted = True
        task.resume_attempted = True
        try:
            task.instance.resume(control)
            inspection = request.restore_request.model_copy(
                update={"operation": request.operation}
            )
            measured, native = task.capture_native(
                inspection, task.inputs(inspection), control
            )
            if task.native_before is None or not task.same_state(
                task.native_before, measured
            ):
                raise OwnershipConflict(
                    "Healthy resumed "
                    + task.label
                    + " state changed original complete baseline"
                )
            payload = self.make_resumed(
                request, restored, native, task.instance.generations[-1].pins
            )
            control.checkpoint()
            return SiteResumeResult(
                request_sha256=request.digest, private_result=payload
            )
        except BaseException:
            task.phase = "quarantined"
            raise
