"""Registered Group family on the same Task/Capture/Restore engine as SSH."""

from collections.abc import Callable
import base64
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from ..instance import GitlabInstance
from ..services import GitlabGeneration
from ..snapshot import GitlabSnapshot, GitlabInventory
from ..group_capture_reader import GroupCaptureReader
from .native_lifecycle import GitlabNativeLifecycle
from .group_spec import GroupSpec
from .group_capture import GroupCapturedFacts, same_group_state
from .group_rules import validate_group_initial
from .group_request import task_input
from .group_recovery import GroupRecoverySnapshot, GroupObserved, GroupRestored
from .group_partial import GroupPartialCapture


def baseline(spec: GroupSpec, facts: GroupCapturedFacts) -> None:
    validate_group_initial(spec, facts.state)


def snapshot(
    request: SiteTaskRequest, state: GitlabSnapshot, native: SitePrivateEvidenceResult
) -> GroupRecoverySnapshot:
    return GroupRecoverySnapshot(request=request, state=state, native_before=native)


def observed(
    request: SiteTaskRequest,
    saved: GroupRecoverySnapshot,
    native: SitePrivateEvidenceResult,
) -> str:
    return GroupObserved(
        request=request, snapshot=saved, native=native
    ).model_dump_json()


def restored(
    request: SiteTaskRequest,
    saved: GroupRecoverySnapshot,
    generation: GitlabGeneration,
    inventory: GitlabInventory,
    native: SitePrivateEvidenceResult,
) -> str:
    assert generation.quiescence is not None
    return GroupRestored(
        request=request,
        snapshot=saved,
        stopped=generation.quiescence,
        gitaly_term=generation.gitaly_term,
        workhorse_terms=generation.workhorse_terms,
        inventory=inventory,
        native=native,
    ).model_dump_json()


class GroupLifecycle(
    GitlabNativeLifecycle[GroupSpec, GroupCapturedFacts, GroupRecoverySnapshot]
):
    def __init__(
        self,
        instance: GitlabInstance,
        reader: GroupCaptureReader,
        username: Callable[[OperationControl], str],
        artifacts: SitePrivateArtifacts,
        *,
        clock: Clock,
        cleanup_controls: OperationControls,
    ) -> None:
        self.group_reader = reader
        self.clock, self.cleanup_controls = clock, cleanup_controls
        super().__init__(
            instance,
            reader,
            username,
            artifacts,
            label="Group",
            collector="gitlab-group-creation",
            inputs=task_input,
            same_state=same_group_state,
            validate_baseline=baseline,
            snapshot=snapshot,
            observed=observed,
            restored=restored,
        )

    def capture_native(
        self, request: SiteTaskRequest, spec: GroupSpec, control: OperationControl
    ) -> tuple[GroupCapturedFacts, SitePrivateEvidenceResult]:
        try:
            return super().capture_native(request, spec, control)
        except BaseException as original:
            # A publication error (including lost acknowledgement) is never
            # followed by another put. Only a failed original read may retain
            # its completed parts, before any complete-envelope put occurred.
            if self.group_reader.last_failure is not original:
                raise
            try:
                operation = request.operation.cleanup(
                    "group-partial-" + request.digest,
                    now=self.clock.utcnow(),
                    seconds=30,
                )
                group_raw, project_raw = (
                    self.group_reader.groups.captured_raw,
                    self.group_reader.projects.captured_raw,
                )
                raw = (
                    GroupPartialCapture(
                        request=request,
                        retention_operation=operation,
                        failed_stage=self.group_reader.failed_stage,
                        group_reply_base64=(
                            None
                            if group_raw is None
                            else base64.b64encode(group_raw).decode()
                        ),
                        project_copy_base64=(
                            None
                            if project_raw is None
                            else base64.b64encode(project_raw).decode()
                        ),
                    )
                    .model_dump_json()
                    .encode()
                )
                if len(raw) > MAX_OBJECT_BYTES:
                    raise ValueError(
                        "Complete partial diagnostic exceeds private CAS bound"
                    )
                result = self.artifacts.publish(
                    request, raw, control=self.cleanup_controls.bind(operation)
                )
                self.last_native_result = result
                setattr(original, "gitlab_partial_native_result", result)
            except BaseException as retention:
                raise BaseExceptionGroup(
                    "Original Group capture and diagnostic retention failures",
                    [original, retention],
                ) from None
            raise
