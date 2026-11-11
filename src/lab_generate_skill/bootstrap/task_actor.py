"""Late binding of existing acquired resources to original current task Actor port."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.ports.task_actor_source import TaskActorSourceBindings
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.actor import ActorRunner
from lab_generate_skill.ports.browser import BrowserActions
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.lifecycle import OperationControls, Clock
from .actor_runtime import original_actor_runtime


@dataclass(frozen=True)
class TaskActorResources:
    scope: ActorExecutionScope
    browser: BrowserActions
    journal: TraceJournal
    calls_root: Path
    completed: list[LocalActorExecution]


class CurrentTaskActorBinding:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        admission: TaskActorSourceBindings,
        resources: Callable[[InitializedTask, PreparedActorInput], TaskActorResources],
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.admission, self.resources, self.evidence, self.controls, self.clock = (
            admission,
            resources,
            evidence,
            controls,
            clock,
        )
        if any(
            value is None for value in (admission, resources, evidence, controls, clock)
        ):
            raise ValueError(
                "Current task Actor requires explicit original resource/source composition"
            )

    def bind(
        self, initialized: InitializedTask, prepared: PreparedActorInput
    ) -> ActorRunner:
        initialized = InitializedTask.model_validate(initialized)
        prepared = PreparedActorInput.model_validate(prepared)
        if (
            initialized.actor.schema_version != "actor-run-request/2"
            or prepared.binding != self.plan.intent.binding
            or initialized.actor.operation != self.plan.operation
        ):
            raise OwnershipConflict(
                "Current task binding cannot downgrade or replace original attempt"
            )
        source = self.admission.authority(self.plan, initialized, prepared)
        resources = self.resources(initialized, prepared)
        read = initialized.actor.operation.model_copy(
            update={
                "operation_id": initialized.actor.operation.operation_id
                + ".task-actor-initial-read"
            }
        )
        snapshot = resources.journal.read(read)
        source.verify(
            initialized.actor, snapshot, self.controls.bind(self.plan.operation)
        )
        runtime = original_actor_runtime(
            initialized.actor,
            resources.journal,
            resources.scope,
            resources.browser,
            self.evidence,
            self.controls,
            self.clock,
            source,
            resources.calls_root,
            resources.completed,
        )
        return runtime.runner
