"""Fixed parent, minimum downstream time, original cleanup and real task consumer."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import (
    OperationStopped,
    OwnershipConflict,
    DispatchAlreadyCommitted,
)
from lab_generate_skill.domain.execution_stage_budget import (
    ExecutionStageBudgets,
    STAGES,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.runtime.bounded_lifecycle import BoundedOperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch


def allocation() -> ExecutionStageBudgets:
    return ExecutionStageBudgets(
        assets_seconds=2,
        source_seconds=3,
        model_seconds=2,
        preparation_seconds=4,
        initialization_seconds=4,
        actor_seconds=6,
        capture_seconds=2,
        judgment_seconds=2,
        task_orchestration_seconds=3,
    )


def case() -> (
    tuple[ManualClock, CancelSwitch, BoundedOperationControls, OperationContext]
):
    clock, cancel = ManualClock(), CancelSwitch()
    owner = ResourceOwner(
        run_id="stages", owner_id="original", job_id="123", worker_id="worker"
    )
    window = OperationWindowBudgets(
        execution_seconds=40,
        cleanup_seconds=10,
        final_margin_seconds=2,
        stop_signal_lead_seconds=12,
    ).window(owner, now=clock.utcnow(), hard_end=clock.utcnow() + timedelta(seconds=52))
    controls = BoundedOperationControls(OperationGuards(clock, cancel), clock, window)
    op = OperationContext(
        operation_id="original",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=window.execution_deadline,
    )
    controls.configure_stages(op, allocation())
    return clock, cancel, controls, op


def test_each_stage_intersects_already_bound_operation_and_parent_never_renews() -> (
    None
):
    clock, _, controls, op = case()
    guard = controls.bind(op)
    original = op.model_dump_json()
    initial = guard.checkpoint()
    for stage in STAGES:
        with controls.stage(stage, op):
            assert guard.checkpoint() == allocation().seconds(stage)
            child = op.model_copy(update={"operation_id": "child-" + stage})
            assert controls.bind(child).checkpoint() == allocation().seconds(stage)
            clock.sleep(0.25)
    assert guard.checkpoint() == initial - 2 and op.model_dump_json() == original
    assert [r["outcome"] for r in controls.stage_observations] == ["completed"] * 8


def test_expensive_stage_rejects_before_side_effect_when_downstream_would_be_starved() -> (
    None
):
    clock, _, controls, op = case()
    clock.sleep(15)
    effects = []
    with pytest.raises(ValueError, match="downstream"):
        with controls.stage("source", op):
            effects.append("started")
    assert effects == []
    assert controls.stage_observations[-1]["outcome"] == "rejected_insufficient_time"


def test_late_actor_cannot_start_with_only_a_few_seconds() -> None:
    clock, _, controls, op = case()
    clock.sleep(31)
    with pytest.raises(ValueError, match="downstream"):
        with controls.stage("actor", op):
            pytest.fail("Actor cannot start")
    assert controls.bind(op).checkpoint() == 9


def test_stage_timeout_preserves_primary_and_independent_cleanup_then_parent() -> None:
    clock, _, controls, op = case()
    first = OSError("unit partial commit")
    cleanup = op.cleanup("original-close", now=clock.utcnow(), seconds=100)
    with pytest.raises(OSError) as seen:
        with controls.stage("preparation", op):
            try:
                clock.sleep(4)
                with pytest.raises(OperationStopped):
                    controls.bind(op).checkpoint()
                raise first
            finally:
                # Cleanup is allowed even while failed phase context is unwinding.
                assert controls.bind(cleanup).checkpoint() == 46
    assert seen.value is first
    assert controls.stage_observations[-1]["error_type"] == "OSError"
    clock.sleep(36)
    with pytest.raises(OperationStopped):
        controls.bind(op).checkpoint()
    assert controls.bind(cleanup).checkpoint() == 10
    clock.sleep(10)
    with pytest.raises(OperationStopped):
        controls.bind(cleanup).checkpoint()


def test_stage_exit_checks_deadline_and_rollback_uses_monotonic_parent() -> None:
    clock, _, controls, op = case()
    with pytest.raises(OperationStopped):
        with controls.stage("initialization", op):
            clock.sleep(4)
            clock.wall -= timedelta(days=1)
    child = op.model_copy(update={"operation_id": "later"})
    assert controls.bind(child).checkpoint() == 36


def test_cleanup_mode_cancellation_invalid_override_duplicate_and_wrong_thread() -> (
    None
):
    clock, _, controls, op = case()
    for bad in (0, -1, True, 3):
        with pytest.raises(ValueError):
            with controls.stage("assets", op, seconds=bad):
                pytest.fail()
    with pytest.raises(OwnershipConflict):
        with controls.stage(
            "source", op.cleanup("close", now=clock.utcnow(), seconds=10)
        ):
            pytest.fail()
    with controls.stage("assets", op):
        with pytest.raises(OwnershipConflict):
            with controls.stage("source", op):
                pytest.fail()
    with pytest.raises(DispatchAlreadyCommitted):
        with controls.stage("assets", op):
            pytest.fail()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: controls.stage("source", op).__enter__())
        with pytest.raises(OwnershipConflict):
            future.result()
    with pytest.raises(OwnershipConflict):
        controls.configure_stages(op, allocation())


@pytest.mark.parametrize(
    "field", [s + "_seconds" for s in STAGES] + ["task_orchestration_seconds"]
)
@pytest.mark.parametrize("bad", [None, 0, -1, True, "10", [], float("inf")])
def test_invalid_budget_rejected(field: str, bad: Any) -> None:
    value = allocation().model_dump()
    value[field] = bad
    with pytest.raises(ValidationError):
        ExecutionStageBudgets.model_validate(value)


def test_exact_current_runtime_composition_and_legacy_wire_remain_separate() -> None:
    from admin_production_task_plan import AdminProductionBudgets
    from production_task_plan import MapProductionBudgets

    w = Path("/anvme/workspace/r102bf10-lab-generate-skill/experiments")
    for folder, kind in (
        ("framework-admin-navigation-production-20261102-v1", AdminProductionBudgets),
        ("framework-map-navigation42-production-20261102-v1", MapProductionBudgets),
    ):
        selected = kind.model_validate_json(
            (
                w / folder / "runtime-stage-budgets-candidate/entry-budgets.json"
            ).read_bytes()
        )
        stages = selected.stage_budgets
        assert stages is not None
        assert (
            stages.execution_seconds <= selected.root_seconds
            and stages.task_seconds == selected.task_seconds
        )
        assert stages.actor_seconds == 3600 and selected.generation_seconds == 600
        for field in ("task_seconds", "post_claim_setup_seconds"):
            raw = selected.model_dump(mode="json")
            raw[field] += 1
            with pytest.raises(ValidationError):
                kind.model_validate(raw)
        raw = selected.model_dump(mode="json")
        raw.pop("stage_budgets")
        with pytest.raises(ValidationError):
            kind.model_validate(raw)
        raw["schema_version"] = selected.schema_version[:-1] + "2"
        legacy = kind.model_validate(raw)
        assert "stage_budgets" not in legacy.model_dump()


@pytest.mark.parametrize(
    "fault", ["none", "preparation", "initialization", "actor", "capture", "judgment"]
)
def test_real_task_consumer_phase_admission_failure_always_keeps_original_cleanup(
    tmp_path: Path, fault: str
) -> None:
    from contextlib import contextmanager
    from collections.abc import Iterator
    from lab_generate_skill.application.execute_task import (
        execute_task,
        TaskExecutionUnconfirmed,
    )
    from lab_generate_skill.domain.execution_stage_budget import ExecutionStage
    from lab_generate_skill.ports.lifecycle import OperationControl
    from task_execution_fixtures import task_case

    c = task_case(tmp_path / "task")
    original = c.deps.controls
    entered = []

    class PhaseControls:
        def bind(self, operation: OperationContext) -> OperationControl:
            return original.bind(operation)

        @contextmanager
        def stage(
            self,
            name: ExecutionStage,
            operation: OperationContext,
            *,
            seconds: int | None = None,
        ) -> Iterator[None]:
            entered.append(name)
            if name == fault:
                raise ValueError("unit insufficient downstream time")
            yield

    deps = replace(c.deps, controls=PhaseControls())
    if fault == "none":
        execute_task(c.plan, deps)
        assert entered == [
            "preparation",
            "initialization",
            "actor",
            "capture",
            "judgment",
        ]
        assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    elif fault == "preparation":
        with pytest.raises(ValueError):
            execute_task(c.plan, deps)
        assert c.phases.calls == [] and c.model.calls == 0
    else:
        with pytest.raises(TaskExecutionUnconfirmed) as seen:
            execute_task(c.plan, deps)
        assert isinstance(seen.value.primary, ValueError)
        assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
        if fault in ("initialization", "actor"):
            assert c.model.calls == 0


def test_existing_source_consumption_before_assets_does_not_reserve_source_twice() -> (
    None
):
    clock, _, controls, op = case()
    with controls.stage("source", op, seconds=1):
        clock.sleep(0.5)
    # All other work fits at 28s, but reserving already verified source again would not.
    clock.sleep(11.5)
    with controls.stage("assets", op):
        assert controls.bind(op).checkpoint() == 2
    assert controls.stage_observations[-1]["downstream_reserved_seconds"] == 23
    with pytest.raises(DispatchAlreadyCommitted):
        with controls.stage(
            "source", op.model_copy(update={"operation_id": "renamed"})
        ):
            pytest.fail()
