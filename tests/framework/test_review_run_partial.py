"""Partial readonly failure and composed deadline/cancellation remain bounded."""

from datetime import timedelta
from typing import Any
import pytest
from lab_generate_skill.application.review_run import review_run, ReviewUnconfirmed
from lab_generate_skill.application.review_controls import ReviewControl
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.runtime.lifecycle import OperationGuards
from construction_review_fixtures import ReviewCase
from test_review_run_boundaries import ready
from test_lifecycle import ManualClock, CancelSwitch, operation


@pytest.mark.parametrize("kind", ["read-failure", "cancel"])
def test_partial_reviewer_preserves_completed_findings_and_primary_without_any_reexecution(
    ready: ReviewCase, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    plan = ready.plan("partial-" + kind)
    deps = ready.deps(plan)
    error = (
        OSError("third original judgment read failed")
        if kind == "read-failure"
        else OperationStopped("CANCELLED", plan.operation.operation_id)
    )

    def failed(*args: Any, **kwargs: Any) -> Evaluation:
        raise error

    monkeypatch.setattr(deps.evaluators[2].evaluator, "evaluate", failed)
    with pytest.raises(ReviewUnconfirmed) as caught:
        review_run(plan, deps)
    assert caught.value.primary is error and len(caught.value.completed) == 2
    assert tuple(f.candidate_slot for f in caught.value.completed) == (0, 1)
    assert all(f.matches_recorded for f in caught.value.completed)
    assert ready.control.source.data.journal().read(plan.operation) == ready.sealed
    assert (
        ready.control.source.native.loader.session.calls == 5
        and len(ready.control.wire.transport.calls) == 1
    )


@pytest.mark.parametrize("shorter", ["parent", "leaf"])
def test_recorded_leaf_wait_cannot_extend_either_original_budget(shorter: str) -> None:
    clock = ManualClock()
    parent = operation(clock).model_copy(
        update={
            "deadline": clock.utcnow()
            + timedelta(seconds=1 if shorter == "parent" else 3)
        }
    )
    child = parent.model_copy(
        update={
            "operation_id": "leaf",
            "deadline": clock.utcnow()
            + timedelta(seconds=1 if shorter == "leaf" else 3),
        }
    )
    controls = OperationGuards(clock, CancelSwitch())
    guard = ReviewControl(controls.bind(parent), controls.bind(child))
    guard.wait(0)
    guard.wait(0.25)
    assert clock.elapsed == pytest.approx(0.25)
    with pytest.raises(OperationStopped) as caught:
        guard.wait(2)
    assert caught.value.reason_code == "DEADLINE_EXCEEDED" and clock.elapsed <= 1.000001


@pytest.mark.parametrize("cancelled", ["parent", "leaf"])
def test_recorded_leaf_wait_preserves_live_parent_and_leaf_cancellation(
    cancelled: str,
) -> None:
    clock, root_cancel, leaf_cancel = ManualClock(), CancelSwitch(), CancelSwitch()
    parent = operation(clock)
    child = parent.model_copy(update={"operation_id": "leaf"})
    guard = ReviewControl(
        OperationGuards(clock, root_cancel).bind(parent),
        OperationGuards(clock, leaf_cancel).bind(child),
    )
    (root_cancel if cancelled == "parent" else leaf_cancel).cancelled = True
    with pytest.raises(OperationStopped) as caught:
        guard.wait(0.2)
    assert caught.value.reason_code == "CANCELLED" and clock.elapsed == 0


@pytest.mark.parametrize("bad", [None, "", True, -1, float("inf"), float("nan")])
def test_invalid_wait_is_rejected_before_clock_advance(bad: Any) -> None:
    clock = ManualClock()
    controls = OperationGuards(clock, CancelSwitch())
    parent = operation(clock)
    child = parent.model_copy(update={"operation_id": "leaf"})
    guard = ReviewControl(controls.bind(parent), controls.bind(child))
    with pytest.raises(ValueError):
        guard.wait(bad)
    assert clock.elapsed == 0
