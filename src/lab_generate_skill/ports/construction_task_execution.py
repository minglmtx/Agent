"""Construction-specific physical admission; shared lifecycle imports only closure rights."""

from typing import Protocol
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from .lifecycle import OperationControl
from .task_execution import TaskClosureAuthority


class TaskExecutionAuthority(TaskClosureAuthority, Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        progress: ConstructionProgress,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        """Original physical source/writer/declaration/evaluator/resource admission,
        full scope/claim/frozen method and exclusive rights. Not a cached grant.
        """
        ...
