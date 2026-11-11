"""Validated lifecycle admission view, distinct from construction progress.

A view conveys scope/limits, never permission; every effect still invokes the
source's live admission and the original resource/closure authorities.
"""

from typing import Literal
from pydantic import Field
from .execution import AttemptBinding
from .validation import Contract


class TaskAdmissionState(Contract):
    schema_version: Literal["task-admission-state/1"] = "task-admission-state/1"
    source_kind: Literal["construction", "execution"]
    binding: AttemptBinding
    max_generations: int = Field(ge=1, le=10000)
    max_interactions: int = Field(ge=1, le=10000)
