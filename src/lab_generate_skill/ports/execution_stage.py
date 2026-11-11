"""Optional selected phase limits; no new task lifecycle or permission supplier."""

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.execution_stage_budget import ExecutionStage
from lab_generate_skill.domain.lifecycle import OperationContext


@runtime_checkable
class ExecutionStageControls(Protocol):
    def stage(
        self,
        name: ExecutionStage,
        operation: OperationContext,
        *,
        seconds: int | None = None,
    ) -> AbstractContextManager[None]: ...
