"""Same-call immutable handoff over real CAS/claim/run producers; rights explicit doubles."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from typing import Any
import pytest
from lab_generate_skill.application.task_state_admission import TaskStateAdmission
from lab_generate_skill.domain.execution import AttemptEvent
from lab_generate_skill.domain.run_journal import AttemptEntry
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseResourceRead,
    TaskPhaseResourceRechecks,
)
from execution_task_phase_fixtures import phase_case


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "claim",
        "storage",
        "resource",
        "cancel",
        "journal",
        "source",
        "partial",
        "final-claim",
        "final-storage",
        "final-cancel",
    ],
)
def test_actual_admission_handoff_keeps_fresh_rights_and_final_source_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    plan, runs = c.plan, c.deps.runs
    control = c.deps.controls.bind(plan.read_operation)
    source = c.source.source_reader
    original = source.load(plan, plan.read_operation, control)
    snapshot = runs.read(plan.read_operation)
    parent = None
    for stage in ("planned", "acquiring"):
        op = plan.operation.model_copy(update={"operation_id": "handoff-" + stage})
        entry = AttemptEntry(
            binding=plan.intent.binding,
            event=AttemptEvent(
                stage=stage,
                operation=op,
                previous_operation_id=parent,
                occurred_at=datetime.now(timezone.utc),
                component_id="handoff-fixture",
                outputs=(
                    (plan.source_ref,)
                    if stage != "planned" and plan.source_ref is not None
                    else ()
                ),
            ),
        )
        snapshot = runs.append(entry, snapshot.revision, op)
        parent = op.operation_id

    class UnitImmutableProof:
        """Explicit fixed-worker return double, never a production source grant."""

        loads = 0
        current = 0

        def load_source(
            self, p: TaskExecutionPlan, op: OperationContext, bounded: OperationControl
        ) -> ExecutionSourceFacts:
            bounded.checkpoint()
            assert p == plan
            self.loads += 1
            return original

        def verify_current(
            self,
            p: TaskExecutionPlan,
            facts: ExecutionSourceFacts,
            op: OperationContext,
            bounded: OperationControl,
        ) -> None:
            bounded.checkpoint()
            assert p == plan and facts == original
            self.current += 1
            if fault == "source":
                raise RevisionConflict("Original immutable source binding changed")
            if self.current == 2:
                if fault == "final-claim":
                    c.source.claim_authority.denied = True
                elif fault == "final-storage":
                    raise PermissionError("Storage revoked at admission return")
                elif fault == "final-cancel":
                    raise OperationStopped("CANCELLED", op.operation_id)
            if fault == "claim":
                c.source.claim_authority.denied = True
            elif fault == "storage":
                raise PermissionError("Original current storage gate revoked")
            elif fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)
            elif fault == "resource":
                c.authority.denied = True

    fixed = UnitImmutableProof()
    source.source_checks = fixed
    held: list[TaskPhaseResourceRead] = []
    read = f.resources.read_for_admission

    def capture(*args: Any, **kwargs: Any) -> TaskPhaseResourceRead:
        value = read(*args, **kwargs)
        held.append(value)
        return value

    monkeypatch.setattr(f.resources, "read_for_admission", capture)
    claim_read = c.source.claims.require_source
    claim_calls: list[OperationContext] = []

    def current_claim(*args: Any, **kwargs: Any) -> Any:
        claim_calls.append(args[3])
        return claim_read(*args, **kwargs)

    monkeypatch.setattr(c.source.claims, "require_source", current_claim)
    if fault == "journal":
        original_read = runs.read
        count = 0

        def changed(op: OperationContext) -> Any:
            nonlocal count
            count += 1
            value = original_read(op)
            return (
                value.model_copy(
                    update={
                        "binding": value.binding.model_copy(
                            update={"submission_key": "changed-current-journal"}
                        )
                    }
                )
                if count == 2
                else value
            )

        monkeypatch.setattr(runs, "read", changed)
    if fault == "partial":

        def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Partial original resource check failed")

        monkeypatch.setattr(c.authority, "verify", fail)
    gate = TaskStateAdmission(f.sources, runs, f.resources, c.source.data.store)

    def admit() -> None:
        gate.verify(
            plan,
            c.phases.closed.reset_plan.scope,
            plan.operation,
            control,
            stages=("acquiring",),
            cleanup_parents=(),
            proof=lambda *args: None,
        )

    if fault == "none":
        admit()
        assert fixed.loads == 1 and fixed.current == 2 and len(claim_calls) == 3
        admit()
        assert fixed.loads == 2 and fixed.current == 4 and len(claim_calls) == 6
        if output := os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
            (Path(output) / "source-admission-read-counts.json").write_text(
                json.dumps(
                    {
                        "fixture_only": True,
                        "original_immutable_proofs_per_admission": 3,
                        "current_immutable_proofs_per_admission": 1,
                        "fresh_current_storage_checks_per_admission": 2,
                        "fresh_source_claim_reads_per_admission": 3,
                        "final_current_source_rights_and_journal_recheck": True,
                        "next_admission_revalidates_all": True,
                        "whole_task_speedup_claim": False,
                    },
                    indent=2,
                )
                + "\n"
            )
    else:
        expected = {
            "source": RevisionConflict,
            "journal": RevisionConflict,
            "cancel": OperationStopped,
            "partial": RuntimeError,
            "claim": OwnershipConflict,
            "storage": PermissionError,
            "resource": PermissionError,
            "final-claim": OwnershipConflict,
            "final-storage": PermissionError,
            "final-cancel": OperationStopped,
        }[fault]
        with pytest.raises(expected):
            admit()
    assert held
    for value in held:
        with pytest.raises(OwnershipConflict):
            _ = value.state
        with pytest.raises(OwnershipConflict):
            value.verify(snapshot, c.phases.closed.reset_plan, control)
    assert c.model.calls == c.browser.calls == 0 and not c.phases.calls


def test_resource_handoff_refuses_cross_thread_repeat_and_closed_use(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    control = c.deps.controls.bind(c.plan.read_operation)
    from lab_generate_skill.application.execution_task_phase_source import (
        ExecutionTaskPhaseSources,
    )

    foreign = ExecutionTaskPhaseSources(c.source.source_reader)
    with pytest.raises(OwnershipConflict):
        f.resources.read_for_admission(
            c.plan, c.plan.read_operation, control, sources=foreign
        )
    loaded = f.resources.read_for_admission(
        c.plan, c.plan.read_operation, control, sources=f.sources
    )
    assert isinstance(loaded, TaskPhaseResourceRechecks)
    with pytest.raises(OwnershipConflict):
        loaded.recheck(control)
    snapshot = c.deps.runs.read(c.plan.read_operation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(lambda: loaded.state).result()
    loaded.verify(snapshot, c.phases.closed.reset_plan, control)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(loaded.recheck, control).result()
    assert loaded.recheck(control) == loaded.state
    with pytest.raises(OwnershipConflict):
        loaded.recheck(control)
    with pytest.raises(OwnershipConflict):
        loaded.verify(snapshot, c.phases.closed.reset_plan, control)
    loaded.close()
    loaded.close()
    with pytest.raises(OwnershipConflict):
        _ = loaded.state
    with pytest.raises(OwnershipConflict):
        loaded.recheck(control)


def test_partial_resource_verification_cannot_supply_a_return_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    control = c.deps.controls.bind(c.plan.read_operation)
    loaded = f.resources.read_for_admission(
        c.plan, c.plan.read_operation, control, sources=f.sources
    )
    assert isinstance(loaded, TaskPhaseResourceRechecks)

    def denied(*args: object) -> None:
        raise PermissionError("Original resource verification revoked")

    monkeypatch.setattr(c.authority, "verify", denied)
    try:
        with pytest.raises(PermissionError):
            loaded.verify(
                c.deps.runs.read(c.plan.read_operation),
                c.phases.closed.reset_plan,
                control,
            )
        with pytest.raises(OwnershipConflict):
            loaded.recheck(control)
    finally:
        loaded.close()
