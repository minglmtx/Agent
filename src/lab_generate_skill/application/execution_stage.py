"""Keep legacy controls unchanged; selected current stage controls enforce caps."""

from contextlib import AbstractContextManager, nullcontext
from lab_generate_skill.domain.execution_stage_budget import ExecutionStage
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.execution_stage import ExecutionStageControls


def execution_stage(
    controls: OperationControls,
    name: ExecutionStage,
    operation: OperationContext,
    *,
    seconds: int | None = None,
) -> AbstractContextManager[None]:
    if isinstance(controls, ExecutionStageControls):
        return controls.stage(name, operation, seconds=seconds)
    return nullcontext()
