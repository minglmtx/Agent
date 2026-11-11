"""Private module diagnostics; candidates explicitly do not prove persistence."""

from typing import Literal
from pydantic import Field
from .task_intent import TaskAttemptIntent as AttemptIntent
from .evidence import EvidenceRef
from .validation import Contract, NonEmptyText


class TaskModuleFailureEvidence(Contract):
    schema_version: Literal["task-module-failure-evidence/1"] = (
        "task-module-failure-evidence/1"
    )
    intent: AttemptIntent
    failure_type: NonEmptyText
    confirmed_references: tuple[EvidenceRef, ...] = Field(max_length=10000)
    candidate_references: tuple[EvidenceRef, ...] = Field(max_length=10000)
    malformed_attributes: tuple[NonEmptyText, ...] = Field(max_length=4)
