"""Normal single-task cleanup consumes one graph; claim/store rights stay fresh."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_phase_source import TaskPhaseRunRead
from execution_task_phase_fixtures import phase_case


@pytest.mark.parametrize("fault", ["none", "claim", "storage", "physical"])
def test_original_cleanup_reads_graph_once_and_rechecks_current_rights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = phase_case(tmp_path / "task")
    c = f.task
    source = c.source.source_reader
    original = source.load(
        c.plan, c.plan.read_operation, c.deps.controls.bind(c.plan.read_operation)
    )

    class UnitProof:
        cleanup_loads = 0
        cleanup_checks = 0

        def load_source(
            self,
            plan: TaskExecutionPlan,
            op: OperationContext,
            control: OperationControl,
        ) -> ExecutionSourceFacts:
            control.checkpoint()
            assert plan == c.plan
            if op.operation_id.startswith("task-cleanup-read-"):
                self.cleanup_loads += 1
            return original

        def verify_current(
            self,
            plan: TaskExecutionPlan,
            facts: ExecutionSourceFacts,
            op: OperationContext,
            control: OperationControl,
        ) -> None:
            control.checkpoint()
            assert plan == c.plan and facts == original
            if op.operation_id.startswith("task-cleanup-read-"):
                self.cleanup_checks += 1
                if self.cleanup_checks == 2:
                    if fault == "claim":
                        c.source.claim_authority.denied = True
                    if fault == "storage":
                        raise PermissionError(
                            "Original cleanup storage revoked at return"
                        )

    proof = UnitProof()
    source.source_checks = proof
    held: list[TaskPhaseRunRead] = []
    open_read = f.sources.open_run_read

    def capture(*args: Any, **kwargs: Any) -> TaskPhaseRunRead:
        value = open_read(*args, **kwargs)
        held.append(value)
        return value

    monkeypatch.setattr(f.sources, "open_run_read", capture)
    if fault == "physical":
        f.cleanup_source.denied = True
    if fault == "none":
        result = execute_task(c.plan, c.deps)
        assert result.evaluation.status == "failure"
        assert proof.cleanup_loads == 2 and proof.cleanup_checks == 4
        assert len(f.cleanup_source.calls) == 2
    else:
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            execute_task(c.plan, c.deps)
        assert caught.value.cleanup_errors
        assert proof.cleanup_loads == 1
        assert len(f.cleanup_source.calls) == 1
        assert "restore" not in c.phases.calls
    assert held
    for handle in held:
        with pytest.raises(OwnershipConflict):
            _ = handle.state
        with pytest.raises(OwnershipConflict):
            _ = handle.run
        with pytest.raises(OwnershipConflict):
            handle.recheck(c.deps.controls.bind(c.plan.read_operation))


def test_cleanup_source_handoff_is_bounded_to_original_thread_and_two_checks(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "task")
    c = f.task
    control = c.deps.controls.bind(c.plan.read_operation)
    handle = f.sources.open_run_read(c.plan, c.plan.read_operation, control)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(lambda: handle.run).result()
        assert handle.run == c.source.run
        assert handle.recheck(control) == handle.state
        assert handle.recheck(control) == handle.state
        with pytest.raises(OwnershipConflict):
            handle.recheck(control)
    finally:
        handle.close()
