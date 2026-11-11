"""Compose the unchanged full Teacher evidence fields from approved parts only."""

from pydantic import JsonValue
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherChatMessage,
)
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.teacher_json import json_text, json_value


def construction_messages(
    scope: TeacherContextScope,
    task: PublicTask,
    teacher_round: int,
    instructions: str,
    initial: str,
    skills: tuple[CompactSkill, ...],
    attempts: tuple[TeacherAttemptView, ...],
    best: int | None,
) -> AllowedTeacherEvidence:
    winner = (
        None
        if best is None
        else {
            "skill": attempts[best].native["skill"],
            "steps": attempts[best].native["steps"],
        }
    )
    body: dict[str, JsonValue] = {
        "task": task.goal,
        "public_task": json_value(task.model_dump(mode="json")),
        "initial_observation": initial,
        "retrieved_skills": [json_value(s.model_payload()) for s in skills],
        "attempts": [json_value(a.native) for a in attempts],
        "best_successful_attempt": winner,
    }
    return AllowedTeacherEvidence(
        scope=scope,
        task=task,
        teacher_round=teacher_round,
        messages=(
            TeacherChatMessage(role="system", content=instructions),
            TeacherChatMessage(role="user", content=json_text(body)),
        ),
    )
