"""Task cleanup phases share one wall/monotonic allowance, including stop paths."""

from datetime import timedelta
from pathlib import Path
import pytest
from lab_generate_skill.application.task_execution_events import TaskExecutionEvents
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.runtime.lifecycle import OperationGuards
from task_execution_fixtures import task_case
from test_lifecycle import ManualClock, CancelSwitch


@pytest.mark.parametrize("change", ["normal", "rollback", "expired"])
def test_close_restore_seal_cannot_renew_task_cleanup(
    tmp_path: Path, change: str
) -> None:
    c = task_case(tmp_path / "task")
    clock = ManualClock()
    clock.wall = c.deps.clock.utcnow()
    events = TaskExecutionEvents(
        c.plan,
        c.deps.runs,
        c.deps.evidence,
        c.deps.controls,
        clock,
        c.deps.runs.read(c.plan.read_operation),
        c.deps.source,
    )
    controls = OperationGuards(clock, CancelSwitch())
    closing = events.operation("closing", cleanup=True)
    budget = c.plan.cleanup_seconds
    assert controls.bind(closing).checkpoint() == budget
    clock.sleep(budget / 2)
    if change == "rollback":
        clock.wall -= timedelta(seconds=100)
    if change == "expired":
        clock.sleep(budget)
    restoring = events.operation("restoring", cleanup=True)
    assert restoring.deadline <= closing.deadline
    if change == "expired":
        with pytest.raises(OperationStopped):
            controls.bind(restoring).checkpoint()
    else:
        assert controls.bind(restoring).checkpoint() == budget / 2
        clock.sleep(1)
        sealed = events.operation("sealed", cleanup=True)
        assert controls.bind(sealed).checkpoint() == budget / 2 - 1
        assert sealed.cancellation_ref is None and sealed.mode == "cleanup"
        assert sealed.parent_operation_id == c.plan.operation.operation_id
