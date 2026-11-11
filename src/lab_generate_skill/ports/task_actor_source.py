"""Business source authority factory for the existing current Actor resource binding."""

from typing import Protocol
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from .actor import ActorRunAuthority


class TaskActorSourceBindings(Protocol):
    def authority(
        self,
        plan: TaskExecutionPlan,
        initialized: InitializedTask,
        prepared: PreparedActorInput,
    ) -> ActorRunAuthority: ...
