"""Explicit capture envelope retains both complete original native replies."""

import base64
from dataclasses import dataclass
from typing import Literal
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.identity import TaskIdentity
from .group_state import GroupNativeState
from ..project_copy import PROJECT_COPY


class GroupCapturePayload(Contract):
    schema_version: Literal["gitlab-group-capture-payload/1"] = (
        "gitlab-group-capture-payload/1"
    )
    task: TaskIdentity
    project_query: str
    group_reply_base64: str
    project_copy_base64: str

    def original_replies(self) -> tuple[bytes, bytes]:
        if self.project_query != PROJECT_COPY:
            raise ValueError("Original fixed selected-project COPY required")
        replies = []
        for value in (self.group_reply_base64, self.project_copy_base64):
            raw = base64.b64decode(value, validate=True)
            if base64.b64encode(raw).decode() != value:
                raise ValueError("Noncanonical complete native reply encoding")
            replies.append(raw)
        return replies[0], replies[1]


@dataclass(frozen=True)
class GroupCapturedFacts:
    state: GroupNativeState
    group_reply: bytes
    project_copy: bytes


def same_group_state(before: GroupCapturedFacts, after: GroupCapturedFacts) -> bool:
    # Byte preservation applies to the original project CSV, not a derived hash
    # substituted for that evidence. Logical SQL rows retain the original fields.
    return before.state == after.state and before.project_copy == after.project_copy
