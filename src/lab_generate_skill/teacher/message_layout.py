"""Render only the already approved messages; keep control/source fields out."""

from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherChatMessage,
    TeacherModelInput,
    native_evidence,
)
from lab_generate_skill.domain.teacher_projection import TeacherProjectionPayload
from .instructions import teacher_projection_guide


def original_messages(source: AllowedTeacherEvidence) -> TeacherModelInput:
    return TeacherModelInput(messages=source.messages)


def shared_messages(
    source: AllowedTeacherEvidence, payload: TeacherProjectionPayload
) -> TeacherModelInput:
    return TeacherModelInput(
        messages=(
            TeacherChatMessage(
                role="system",
                content=source.messages[0].content
                + teacher_projection_guide(native_evidence(source.messages[1].content)),
            ),
            TeacherChatMessage(role="user", content=payload.model_dump_json()),
        )
    )
