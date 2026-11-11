"""Two fixed readonly commands, one explicit envelope; no retries or admission."""

import base64
from collections.abc import Callable
from typing import Literal
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.ports.lifecycle import OperationControl
from .group_native_reader import GitlabGroupNativeReader
from .project_copy import GitlabProjectCopyReader, PROJECT_COPY
from .tasks.group_spec import GroupSpec
from .tasks.group_capture import GroupCapturedFacts, GroupCapturePayload


class GroupCaptureReader:
    def __init__(
        self,
        groups: GitlabGroupNativeReader,
        projects: GitlabProjectCopyReader,
        decode: Callable[[bytes, GroupSpec], GroupCapturedFacts],
    ) -> None:
        self.groups, self.projects, self.decode = groups, projects, decode
        self.captured_raw: bytes | None = None
        self.last_failure: BaseException | None = None
        self.failed_stage: Literal["groups", "projects", "envelope"] = "groups"

    def capture(
        self, spec: GroupSpec, username: str, control: OperationControl
    ) -> GroupCapturedFacts:
        self.captured_raw = None
        self.groups.captured_raw = self.projects.captured_raw = None
        self.last_failure = None
        self.failed_stage = "groups"
        try:
            return self._capture(spec, username, control)
        except BaseException as error:
            self.last_failure = error
            raise

    def _capture(
        self, spec: GroupSpec, username: str, control: OperationControl
    ) -> GroupCapturedFacts:
        spec = GroupSpec.model_validate(spec)
        state = self.groups.capture(spec, username, control)
        group_raw = self.groups.captured_raw
        if group_raw is None:
            raise RuntimeError("Original complete Group reply unavailable")
        self.failed_stage = "projects"
        project_raw = self.projects.capture(spec, control)
        self.failed_stage = "envelope"
        payload = GroupCapturePayload(
            task=spec.task,
            project_query=PROJECT_COPY,
            group_reply_base64=base64.b64encode(group_raw).decode(),
            project_copy_base64=base64.b64encode(project_raw).decode(),
        )
        raw = payload.model_dump_json().encode()
        if len(raw) > MAX_OBJECT_BYTES:
            raise ValueError("Complete combined Group replies exceed private CAS bound")
        self.captured_raw = raw
        value = self.decode(raw, spec)
        if (
            value.state != state
            or value.group_reply != group_raw
            or value.project_copy != project_raw
        ):
            raise ValueError("Group decoder changed original captured replies")
        control.checkpoint()
        return value
