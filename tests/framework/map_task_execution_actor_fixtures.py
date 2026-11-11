"""Existing current Actor scope/wire/count/context/trace; native services synthetic."""

import copy
from typing import Any, cast
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.bootstrap.map_task_execution import MapTaskExecution
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.bootstrap.execution_task import RecordedExecutionTask
from lab_generate_skill.bootstrap.task_actor import TaskActorResources
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan, TraceCapacity
from lab_generate_skill.ports.lifecycle import OperationControl
from map_task_preparation_port_fixtures import MapPreparationPortCase
from map_task_execution_initialization_fixtures import CurrentMapHandles
from source_actor_trace import SourceTraceAuthority


class UnitMapActorSource:
    def __init__(self, p: MapPreparationPortCase, native: Any) -> None:
        self.p, self.native = p, native
        self.bundle: (
            MapTaskExecution[RecordedConstructionTask]
            | MapTaskExecution[RecordedExecutionTask]
            | None
        ) = None
        self.denied, self.calls = False, 0

    def verify(
        self,
        request: ActorRunRequest,
        snapshot: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise OwnershipConflict("Synthetic original Map Actor source denied")
        self.calls += 1
        assert self.bundle is not None
        initialized = self.bundle.initialization.original().state.result
        assert initialized is not None and request == initialized.actor
        assert request.model_allocation == self.native.scope.binding.resource
        assert request.scope == self.p.reset.scope
        assert snapshot.plan.binding == self.p.plan.intent.binding
        assert self.native.client.owner_guard == self.native.scope.guard


def current_map_actor_resources(
    p: MapPreparationPortCase,
    native: Any,
    handles: CurrentMapHandles,
    initialized: InitializedTask,
    prepared: PreparedActorInput,
) -> TaskActorResources:
    assert handles.browser is not None and handles.browser.phase == "open"
    if handles.trace is not None:
        raise DispatchAlreadyCommitted(
            "Original Map trace/Actor resources already constructed"
        )
    assert prepared.binding == p.plan.intent.binding
    store, controls = p.original.resource.evidence, p.original.resource.controls
    request = initialized.actor
    assert request.model_allocation.owner == p.original.scope.owner
    root = p.original.workspace / "current-original-trace"
    calls = p.original.workspace / "current-original-model-calls"
    root.mkdir()
    calls.mkdir()
    plan = TracePlan(
        binding=p.plan.intent.binding,
        scope=request.scope,
        initial_observation_ref=request.initial_observation_ref,
        max_generations=1,
        max_interactions=1,
        capacity=TraceCapacity(
            max_events=128,
            max_bytes=4 * 1024**2,
            max_event_bytes=65536,
            max_trace_bytes=4 * 1024**2,
        ),
    )
    completed: list[LocalActorExecution] = []
    journal = FileTraceJournal(
        root,
        plan,
        controls,
        store,
        SourceTraceAuthority(plan, store, controls, completed),
    )
    handles.trace, handles.completed = journal, completed
    operation = p.plan.operation.model_copy(
        update={"operation_id": p.plan.operation.operation_id + ".current-trace-create"}
    )
    journal.create(plan, operation)
    scope = copy.copy(native.scope)
    scope.evidence = ActorEvidence(store)
    return TaskActorResources(
        cast(ActorExecutionScope, scope),
        handles.browser.session,
        journal,
        calls,
        completed,
    )
