"""Cleanup joins original frozen journals; source/physical permission stays fake."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from task_cleanup_admission_fixtures import cleanup_case


@pytest.mark.parametrize("stopped", [False, True])
def test_acknowledged_original_cleanup_rechecks_claim_full_plan_and_mandatory_source(
    tmp_path: Path, stopped: bool
) -> None:
    fixture = cleanup_case(tmp_path / "task")
    c, bridge, d = fixture.task, fixture.bridge, fixture.declaration
    calls = []

    class Finalization:
        def close(
            self,
            plan: TaskExecutionPlan,
            reset: Any,
            operation: OperationContext,
            control: OperationControl,
        ) -> ClosedTaskResources:
            bridge.verify(plan, d, c.phases.closed.closure_refs, operation, control)
            calls.append("closing")
            return c.phases.close(plan, reset, operation, control)

        def restore(
            self,
            plan: TaskExecutionPlan,
            closed: ClosedTaskResources,
            operation: OperationContext,
            control: OperationControl,
        ) -> EvidenceRef:
            bridge.verify(plan, d, closed.closure_refs, operation, control)
            calls.append("restoring")
            return c.phases.restore(plan, closed, operation, control)

    c.deps = replace(c.deps, finalization=Finalization())
    if stopped:
        c.phases.errors["capture"] = OperationStopped(
            "CANCELLED", c.plan.operation.operation_id
        )
        with pytest.raises(TaskExecutionUnconfirmed):
            execute_task(c.plan, c.deps)
    else:
        assert execute_task(c.plan, c.deps).evaluation.status == "failure"
    assert calls == ["closing", "restoring"] and len(fixture.source.calls) == 2
    with pytest.raises(OwnershipConflict):
        bridge.verify(
            c.plan, d, (), c.plan.operation, c.deps.controls.bind(c.plan.operation)
        )


@pytest.mark.parametrize("bad", [None, {}, [], True, "missing"])
def test_bad_cleanup_declaration_rejected_without_journal_changes(
    tmp_path: Path, bad: Any
) -> None:
    f = cleanup_case(tmp_path / "task")
    c = f.task
    before = c.deps.runs.read(c.plan.read_operation)
    operation = c.plan.operation.cleanup(
        "bad-cleanup", now=c.deps.clock.utcnow(), seconds=10
    )
    with pytest.raises((TypeError, ValueError)):
        f.bridge.verify(c.plan, bad, (), operation, c.deps.controls.bind(operation))
    assert c.deps.runs.read(c.plan.read_operation) == before and f.source.calls == []
