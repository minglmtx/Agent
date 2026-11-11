"""Explicit complete allowed Teacher format; construction grants no permission.

Only the already approved messages become model-visible. Scope/round/task bind
provenance outside those messages; authority must approve their original source.
The producer must exclude unapproved DB, answers and private containers before
constructing this evidence; this data type does not grant or prove permission.
"""

from typing import Literal, Self
from pydantic import Field, JsonValue, model_validator
from .validation import Contract
from .teacher_scope import TeacherContextScope
from .task import PublicTask
from .teacher_json import MAX_TEACHER_BYTES, read_json, object_value, array_value

PAGE_FIELDS = ("axtree_txt", "axtree_full_txt", "observation")
PROTOCOL_FIELDS = ("observation_scope", "observation_mode", "observation_policy")


def observation_body(message: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    import json

    content = message.get("content")
    if message.get("role") != "user" or not isinstance(content, str) or not content:
        return None
    try:
        parsed = read_json(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def native_evidence(raw: str) -> dict[str, JsonValue]:
    evidence = object_value(
        read_json(raw), "Complete native Teacher evidence object required"
    )
    if (
        type(evidence.get("task")) is not str
        or type(evidence.get("initial_observation")) is not str
    ):
        raise ValueError("Original task and complete initial page strings required")
    attempts = array_value(evidence.get("attempts"), "All original attempts required")
    if not attempts or len(attempts) > 10000:
        raise ValueError("Teacher revision requires bounded nonempty complete attempts")
    total = 0
    for value in attempts:
        attempt = object_value(value, "Each complete attempt must be an object")
        if {"candidate_index", "events"} & set(attempt):
            raise ValueError("Reserved projected fields in original attempt")
        messages = array_value(
            attempt.get("trajectory"), "Every original trajectory required"
        )
        total += len(messages)
        if total > 100000:
            raise ValueError("Complete Teacher event audit exceeds format bound")
        for item in messages:
            message = object_value(item, "Every original trajectory message required")
            role = message.get("role")
            if type(role) is not str or not role.strip() or "content" not in message:
                raise ValueError(
                    "Explicit original role and content required, including null"
                )
            body = observation_body(message)
            if body is not None:
                for key in PAGE_FIELDS:
                    if (
                        key in body
                        and body[key] is not None
                        and not isinstance(body[key], str)
                    ):
                        raise ValueError(
                            "Unsupported native page-field type; retain source and refuse"
                        )
    return evidence


class TeacherChatMessage(Contract):
    role: Literal["system", "user"]
    content: str


class TeacherModelInput(Contract):
    """Exact existing OpenRouter input shape, not a control envelope."""

    messages: tuple[TeacherChatMessage, TeacherChatMessage]

    @model_validator(mode="after")
    def original_pair(self) -> Self:
        if tuple(m.role for m in self.messages) != ("system", "user"):
            raise ValueError("Original complete system/user Teacher pair required")
        if len(self.model_dump_json().encode()) > MAX_TEACHER_BYTES:
            raise ValueError("Complete Teacher model input exceeds byte bound")
        return self


class AllowedTeacherEvidence(Contract):
    schema_version: Literal["teacher-input/1"] = "teacher-input/1"
    format_version: Literal["teacher-native-complete/1"] = "teacher-native-complete/1"
    scope: TeacherContextScope
    task: PublicTask
    teacher_round: int = Field(ge=1, le=3)
    messages: tuple[TeacherChatMessage, TeacherChatMessage]

    @model_validator(mode="after")
    def complete_approved_shape(self) -> Self:
        TeacherModelInput(messages=self.messages)
        evidence = native_evidence(self.messages[1].content)
        if self.task.identity != self.scope.task or evidence["task"] != self.task.goal:
            raise ValueError("Teacher allowed evidence changed original task/scope")
        if len(self.model_dump_json().encode()) > MAX_TEACHER_BYTES:
            raise ValueError("Complete allowed Teacher source exceeds byte bound")
        return self
