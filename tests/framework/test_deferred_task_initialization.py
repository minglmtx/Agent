"""The current entry constructs its original initializer after prepare, once."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.bootstrap.task_initialization import DeferredTaskInitialization
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from task_execution_fixtures import task_case, UnitPhases


@pytest.mark.parametrize("fault", ["none", "factory-error", "empty", "wrong-type"])
def test_late_original_factory_runs_after_prepare_once_and_retains_failure(
    tmp_path: Path, fault: str
) -> None:
    c = task_case(tmp_path / "task")
    calls = []
    original_error = TimeoutError(
        "Synthetic initializer construction acknowledgement lost"
    )

    def build(
        plan: TaskExecutionPlan, operation: OperationContext, control: OperationControl
    ) -> Any:
        control.checkpoint()
        assert c.phases.calls[-1] == "prepare"
        assert plan == c.plan and operation.operation_id.endswith(".starting")
        calls.append(operation)
        if fault == "factory-error":
            raise original_error
        if fault == "empty":
            return None
        if fault == "wrong-type":
            return []
        return c.phases

    late = DeferredTaskInitialization[UnitPhases](c.plan, build)
    with pytest.raises(OwnershipConflict):
        late.original()
    assert calls == []
    c.deps = replace(c.deps, initialization=late)
    if fault == "none":
        assert execute_task(c.plan, c.deps).evaluation.status == "failure"
        assert late.original() is c.phases
    else:
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            execute_task(c.plan, c.deps)
        if fault == "factory-error":
            assert caught.value.primary is original_error
        assert "model" not in c.phases.calls and "close" in c.phases.calls
    assert len(calls) == 1
    op = c.plan.operation.model_copy(
        update={"operation_id": c.plan.operation.operation_id + ".starting"}
    )
    with pytest.raises(DispatchAlreadyCommitted):
        late.start(c.plan, op, c.deps.controls.bind(op))
    assert len(calls) == 1
