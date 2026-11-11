"""Single-task physical source authority; common phase/lifecycle code stays neutral."""

from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_resource_owner import OriginalTaskResourceOwner


class OriginalExecutionTaskAuthority:
    def __init__(self, resources: OriginalTaskResourceOwner) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner):
            raise TypeError("Actual original task resource owner required")
        self.resources = resources

    def verify(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        r = self.resources
        if (
            plan != r.plan
            or source.source.intent != plan.intent
            or source.source.run != snapshot.binding
            or source.source.task != r.owner.task
            or reset.scope.owner != r.owner.run.owner
            or reset.scope.task != r.owner.task.identity
            or reset.scope.attempt_id != plan.intent.binding.attempt_id
        ):
            raise OwnershipConflict(
                "Actual task resources changed original source/reset/run"
            )
        # Bounded historical ownership reads are also valid during cleanup. The
        # existing phase admission separately gates new effects on the run state.
        r.require(r.bounded_read(control), control, live=False)

    def verify_initial(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        facts: CandidateFacts,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> None:
        r = self.resources
        if (
            plan != r.plan
            or source.source.intent != plan.intent
            or snapshot.binding != r.owner.run
            or facts.source != source.context
            or facts.task_binding != r.owner.task
            or facts.baseline.scope.owner != r.owner.run.owner
        ):
            raise OwnershipConflict(
                "Actor handoff changed original source/initial facts"
            )
        browser = r.require_browser(plan.operation, control)
        if (
            browser.session.observation_ref != facts.baseline.observation_ref
            or facts.observation.record.sequence != 0
            or facts.equivalence.status != "equivalent"
            or facts.baseline.status != "ready"
        ):
            raise OwnershipConflict(
                "Actual unique initial view and measured equivalence required"
            )

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.resources.verify_closed(plan, closed, operation, control)
