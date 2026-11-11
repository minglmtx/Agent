"""Production constructors from owned initialization through prepared worker and closure."""

from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs
import map_task_preparation_port_fixtures as preparation
import map_task_execution_initialization_fixtures as initialization


@pytest.mark.parametrize("revoke", [False, True])
def test_owned_initialization_selects_window_and_rechecks_final_permission(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    revoke: bool,
) -> None:
    original_prepare = preparation.bind_preparation
    selected = ActorGenerationBudgets(preparation_seconds=60, execution_seconds=60)

    def prepare(*args: Any, **kwargs: Any) -> Any:
        return original_prepare(*args, **kwargs, execution_seconds=600)

    def actor(**kwargs: Any) -> TaskActorInitialization:
        return TaskActorInitialization(**kwargs, generation_budgets=selected)

    monkeypatch.setattr(preparation, "bind_preparation", prepare)
    monkeypatch.setattr(initialization, "TaskActorInitialization", actor)
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, owner):
        fixed = fixed_task_source_inputs(c, owner, monkeypatch)
        original_inputs = RecordedLocalActorModel._inputs
        gates = 0

        def inputs(self: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal gates
            gates += 1
            assert self._clock is not None
            if revoke and gates == 3:
                fixed.denied = True
            return original_inputs(self, *args, **kwargs)

        monkeypatch.setattr(RecordedLocalActorModel, "_inputs", inputs)
        if revoke:
            with pytest.raises(TaskExecutionUnconfirmed):
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert gates == 3 and c.native.loader.session.calls == 0
            assert not c.handles.completed
        else:
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert gates == 3 and c.native.loader.session.calls == 1
            actual = c.handles.completed[0]
            assert actual.call.intent.execution_window.budgets == selected
            assert (
                actual.dispatch_timing.operation.deadline
                - actual.dispatch_timing.started_at
                == timedelta(seconds=60)
            )
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        assert owner.inputs is not None and not owner.inputs.active
