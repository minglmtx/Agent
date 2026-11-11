"""Shared phase source logic with no construction record; exact live rights remain mandatory."""

from pathlib import Path
import ast, subprocess, sys
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    OperationStopped,
    DispatchAlreadyCommitted,
)
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_phase_fixtures import phase_case
from test_run_journal import command


@pytest.mark.parametrize("stopped", [False, True])
def test_single_source_shared_preparation_full_plan_cleanup_and_complete_lifecycle(
    tmp_path: Path, stopped: bool
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    if stopped:
        c.phases.errors["capture"] = OperationStopped(
            "CANCELLED", c.plan.operation.operation_id
        )
        with pytest.raises(TaskExecutionUnconfirmed):
            execute_task(c.plan, c.deps)
    else:
        result = execute_task(c.plan, c.deps)
        assert result.evaluation.status == "failure"
    assert not hasattr(c.deps, "construction")
    assert len(f.cleanup_source.calls) == 2
    assert all(
        op.mode == "cleanup" and op.attempt_id == c.plan.intent.binding.attempt_id
        for op in f.cleanup_source.calls
    )
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before


@pytest.mark.parametrize("fault", ["source", "resources", "cleanup"])
def test_source_or_resource_revocation_never_becomes_cached_permission(
    tmp_path: Path, fault: str
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    if fault == "source":
        c.source.claim_authority.denied = True
    elif fault == "resources":
        c.authority.denied = True
    else:
        f.cleanup_source.denied = True
    with pytest.raises((OwnershipConflict, PermissionError, TaskExecutionUnconfirmed)):
        execute_task(c.plan, c.deps)
    if fault != "cleanup":
        assert c.model.calls == c.browser.calls == 0
    else:
        assert c.model.calls == 1 and "restore" not in c.phases.calls


def test_source_run_read_scope_and_frozen_plan_cannot_change(tmp_path: Path) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    control = c.deps.controls.bind(c.plan.read_operation)
    state = f.sources.read(c.plan, c.plan.read_operation, control)
    assert state.task == c.source.source.task and state.intent == c.plan.intent
    assert f.sources.read(c.plan, c.plan.read_operation, control) == state
    wrong = RunPlan.model_validate(
        {
            **c.source.run.model_dump(),
            "resources": {
                **c.source.run.resources.model_dump(),
                "cleanup_timeout_seconds": 31,
            },
        }
    )
    with pytest.raises(OwnershipConflict):
        f.sources.verify_run(c.plan, state, wrong, c.plan.read_operation, control)
    with pytest.raises(OwnershipConflict):
        c.source.source_reader.load(c.plan, c.plan.operation, control)
    assert not c.phases.calls


def test_bounded_cleanup_source_read_does_not_use_expired_execute_scope(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    read = c.plan.read_operation.cleanup(
        "owned-cleanup-read", now=c.deps.clock.utcnow(), seconds=20
    )
    assert (
        f.sources.read(c.plan, read, c.deps.controls.bind(read)).intent == c.plan.intent
    )
    assert not c.phases.calls


def test_common_phases_have_no_construction_state_or_training_dependency() -> None:
    root = Path(__file__).resolve().parents[2] / "src/lab_generate_skill/application"
    for name in (
        "task_state_admission",
        "task_preparation_admission",
        "task_initialization_admission",
        "task_capture_admission",
        "task_finalization_admission",
    ):
        tree = ast.parse((root / (name + ".py")).read_text())
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not attrs.intersection(
            {
                "construction",
                "pending_attempt",
                "candidate_slot",
                "revision_round",
                "source_kind",
            }
        )
    program = """
import sys
from lab_generate_skill.application.task_preparation_admission import TaskPreparationAuthority
from lab_generate_skill.application.task_initialization_admission import TaskInitializationAuthority
from lab_generate_skill.application.task_capture_admission import TaskCaptureAuthority
from lab_generate_skill.application.task_finalization_admission import TaskFinalizationAuthority
from lab_generate_skill.application.execution_task_phase_source import ExecutionTaskPhaseSources
assert 'lab_generate_skill.domain.construction_state' not in sys.modules
assert 'lab_generate_skill.application.admit_candidate' not in sys.modules
"""
    subprocess.run([sys.executable, "-B", "-c", program], check=True)


def test_phase_resource_gate_rechecks_after_outer_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
    from lab_generate_skill.domain.task_execution import TaskExecutionPlan
    from lab_generate_skill.domain.run_journal import RunSnapshot
    from lab_generate_skill.domain.reset import ResetPlan

    f = phase_case(tmp_path / "single")
    c = f.task
    verify = c.authority.verify
    calls = 0

    def revoke(
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls >= 3:
            c.authority.denied = True
        verify(plan, source, snapshot, reset, control)

    monkeypatch.setattr(c.authority, "verify", revoke)
    with pytest.raises(TaskExecutionUnconfirmed):
        execute_task(c.plan, c.deps)
    assert calls == 3 and c.model.calls == c.browser.calls == 0
    assert "acquire" not in c.phases.calls
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


def test_phase_source_view_does_not_grant_authority_when_forged(tmp_path: Path) -> None:
    from lab_generate_skill.domain.errors import RevisionConflict

    f = phase_case(tmp_path / "single")
    c = f.task
    control = c.deps.controls.bind(c.plan.read_operation)
    original = f.sources.read(c.plan, c.plan.read_operation, control)
    wrong = original.model_copy(update={"source_sha256": "0" * 64})
    snapshot = c.deps.runs.read(c.plan.read_operation)
    with pytest.raises(RevisionConflict):
        f.resources.verify(
            c.plan,
            wrong,
            snapshot,
            c.phases.closed.reset_plan,
            c.plan.read_operation,
            control,
        )
    assert not c.phases.calls


def test_single_origin_proof_reverifies_original_source_without_constructing_progress(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.application.execution_task_phase_source import (
        ExecutionTaskOriginSource,
    )

    f = phase_case(tmp_path / "single")
    c = f.task
    proof = ExecutionTaskOriginSource(c.plan, f.sources, c.deps.controls)
    before = proof.verify_source(c.plan.read_operation)
    assert before == f.sources.read(
        c.plan, c.plan.read_operation, c.deps.controls.bind(c.plan.read_operation)
    )
    c.source.claim_authority.denied = True
    with pytest.raises(OwnershipConflict):
        proof.verify_source(c.plan.read_operation)
    assert not c.phases.calls
