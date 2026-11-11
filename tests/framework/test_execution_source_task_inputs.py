"""Original CAS/claim facts across one task; fixed-worker/current gates doubled."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_phase_fixtures import phase_case


@pytest.mark.parametrize(
    "fault",
    ["none", "storage", "claim", "cancel", "plan", "thread", "reader", "partial"],
)
def test_owned_task_source_body_handoff_keeps_each_current_gate(
    tmp_path: Path, fault: str
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    plan = c.plan
    source = c.source.source_reader
    op = plan.read_operation
    control = c.deps.controls.bind(op)
    original = source.load(plan, op, control)

    class Fixed:
        loads = 0
        current = 0

        def load_source(
            self,
            p: TaskExecutionPlan,
            operation: OperationContext,
            bounded: OperationControl,
        ) -> ExecutionSourceFacts:
            assert p == plan
            bounded.checkpoint()
            self.loads += 1
            if fault == "partial":
                raise OSError("Fixed source proof did not return")
            return original

        def verify_current(
            self,
            p: TaskExecutionPlan,
            facts: ExecutionSourceFacts,
            operation: OperationContext,
            bounded: OperationControl,
        ) -> None:
            assert p == plan and facts == original
            bounded.checkpoint()
            self.current += 1
            if fault == "storage":
                raise PermissionError("Current store revoked")
            if fault == "cancel":
                raise OperationStopped("CANCELLED", operation.operation_id)
            if fault == "claim":
                c.source.claim_authority.denied = True

    fixed = Fixed()
    source.source_checks = fixed

    def consume() -> None:
        with source.task_scope(plan):
            assert source.load(plan, op, control) == original
            if fault == "plan":
                assert plan.source_ref is not None
                wrong = TaskExecutionPlan.model_validate(
                    plan.model_copy(
                        update={
                            "source_ref": plan.source_ref.model_copy(
                                update={"producer": "different-original-source"}
                            )
                        }
                    )
                )
                source.load(wrong, op, control)
            elif fault == "thread":
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(source.load, plan, op, control).result()
            elif fault == "reader":
                source.source_checks = Fixed()
                source.load(plan, op, control)
            else:
                assert source.load(plan, op, control) == original
                assert source.load(plan, op, control) == original

    if fault == "none":
        consume()
        assert fixed.loads == 1 and fixed.current == 2
        # Independent reads still obtain the graph, never inheriting this scope.
        assert source.load(plan, op, control) == original
        assert fixed.loads == 2
    else:
        with pytest.raises(
            (OwnershipConflict, PermissionError, OperationStopped, OSError)
        ):
            consume()
        assert fixed.loads == 1
    assert source._task_facts is None and source._task_plan is None
    with pytest.raises(OwnershipConflict):
        with source.task_scope(plan):
            pass
