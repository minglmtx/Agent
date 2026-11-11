"""Common completed task and original publication context, without business conversion."""

from dataclasses import dataclass
from lab_generate_skill.domain.task_completion import TaskCompletionFacts
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.evaluation import Evaluation
from .task_execution_events import TaskExecutionEvents


@dataclass(frozen=True)
class CompletedTaskExecution:
    plan: TaskExecutionPlan
    facts: TaskCompletionFacts
    evaluation: Evaluation
    initialized: InitializedTask
    trace: TraceSnapshot
    events: TaskExecutionEvents

    @property
    def intent(self) -> TaskAttemptIntent:
        return self.facts.intent

    @property
    def generations(self) -> int:
        return self.facts.generations

    @property
    def interactions(self) -> int:
        return self.facts.interactions
