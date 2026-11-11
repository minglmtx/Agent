"""Current 64K Actor binding/default assembly; lifecycle/physical facts synthetic.

This is the composition module gate, not the complete Map producer join.
"""

from dataclasses import replace
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.bootstrap.task_execution_composition import (
    TaskExecutionServices,
    TaskExecutionRuntime,
    bind_task_execution,
)
from lab_generate_skill.bootstrap.task_initialization import DeferredTaskInitialization
from lab_generate_skill.bootstrap.task_actor import (
    CurrentTaskActorBinding,
    TaskActorResources,
)
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import InitializedTask, TaskExecutionPlan
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from source_actor_context_fixtures import source_context_case
from task_actor_v2_fixtures import current_task_case
from actor_long_fixtures import long_config
from test_run_journal import command
from task_execution_fixtures import UnitPhases


@pytest.mark.parametrize("missing_source", [False, True])
def test_current_entry_composes_existing_actor_with_original_journals_and_late_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_source: bool
) -> None:
    native = source_context_case(
        tmp_path / "native64", monkeypatch, engine_config=long_config()
    )
    current = current_task_case(tmp_path / "current", monkeypatch, shared_native=native)
    c = current.task
    calls = []

    def initializer(
        plan: TaskExecutionPlan, op: OperationContext, control: OperationControl
    ) -> UnitPhases:
        control.checkpoint()
        assert c.phases.calls[-1] == "prepare"
        calls.append("initializer")
        return c.phases

    def resources(
        initialized: InitializedTask, prepared: PreparedActorInput
    ) -> TaskActorResources:
        assert (
            initialized == c.phases.initialized
            and prepared.binding == c.plan.intent.binding
        )
        calls.append("resources")
        return current.resources

    late = DeferredTaskInitialization(c.plan, initializer)
    services = TaskExecutionServices(
        c.deps.preparation,
        late,
        c.deps.capture,
        c.deps.evaluator,
        c.deps.finalization,
        c.deps.states,
        c.deps.admission.inputs,
    )
    runtime = TaskExecutionRuntime(
        c.deps.construction,
        c.deps.runs,
        c.deps.admission.claims,
        EvidenceRunPlans(c.deps.evidence, c.deps.controls),
        c.deps.authority,
        c.deps.admission.authority,
        current.source,
        c.deps.evidence,
        c.deps.controls,
        c.deps.clock,
    )
    before = c.deps.runs.read(c.plan.read_operation)
    try:
        if missing_source:
            runtime = replace(runtime, actor_source=cast(ActorRunAuthority, None))
            with pytest.raises(ValueError):
                bind_task_execution(c.plan, services, runtime, resources)
            assert c.deps.runs.read(c.plan.read_operation) == before
            assert calls == [] and native.loader.session.calls == 0
        else:
            task = bind_task_execution(c.plan, services, runtime, resources)
            assert isinstance(task.deps.actors, CurrentTaskActorBinding)
            assert calls == [] and native.loader.session.calls == 0
            result = task.execute(c.plan.intent, c.plan.operation)
            assert result.evaluation.status == "failure"
            assert calls == ["initializer", "resources"]
            assert (
                result.generations
                == result.interactions
                == len(current.completed)
                == native.loader.session.calls
                == 1
            )
            request = late.original().initialized.actor
            assert request.schema_version == "actor-run-request/2"
            assert native.scope.spec.engine_config.context_window == 65536
            assert (
                native.params.max_input_tokens == 61440
                and native.params.max_new_tokens == 4096
            )
            with pytest.raises(DispatchAlreadyCommitted):
                task.execute(c.plan.intent, c.plan.operation)
            assert native.loader.session.calls == 1
    finally:
        native.client.close(c.deps.controls.bind(command("composition-native-close")))
