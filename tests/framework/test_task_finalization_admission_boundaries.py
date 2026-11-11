"""Original cleanup scope/claim/history and stopped-run boundaries; no source effects."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunEvent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunEntry
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from task_cleanup_admission_fixtures import cleanup_case


@pytest.mark.parametrize(
    "fault",
    [
        "foreign-attempt",
        "parent",
        "declaration",
        "planned-bytes",
        "claim-denied",
        "source-denied",
        "journal-race",
        "stage",
    ],
)
def test_unqualified_cleanup_cannot_borrow_original_source_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = cleanup_case(tmp_path / "task")
    c, bridge, d = f.task, f.bridge, f.declaration
    checked = []

    class Finalization:
        def close(
            self,
            plan: TaskExecutionPlan,
            reset: Any,
            operation: OperationContext,
            control: OperationControl,
        ) -> ClosedTaskResources:
            with monkeypatch.context() as patch:
                wrong_plan, wrong_d, wrong_op = plan, d, operation
                expected: type[Exception] = OwnershipConflict
                if fault == "foreign-attempt":
                    wrong_op = operation.model_copy(
                        update={"attempt_id": "foreign-attempt"}
                    )
                elif fault == "parent":
                    wrong_op = operation.model_copy(
                        update={"parent_operation_id": "foreign-task"}
                    )
                elif fault == "declaration":
                    wrong_d = d.model_copy(
                        update={"reset_operation_id": "foreign-reset"}
                    )
                elif fault == "planned-bytes":
                    wrong_plan = plan.model_copy(
                        update={
                            "skill_ref": plan.skill_ref.model_copy(
                                update={"sha256": "f" * 64}
                            )
                        }
                    )
                elif fault == "claim-denied":

                    def denied(*args: Any, **kwargs: Any) -> Any:
                        raise PermissionError("Synthetic original claim access denied")

                    patch.setattr(bridge.claims, "require", denied)
                    expected = PermissionError
                elif fault == "source-denied":
                    patch.setattr(f.source, "denied", True)
                    expected = PermissionError
                else:
                    original = c.deps.runs.read
                    count = 0

                    def changed(op: OperationContext) -> Any:
                        nonlocal count
                        count += 1
                        snap = original(op)
                        if fault == "stage":
                            return snap.model_copy(
                                update={"entries": snap.entries[:-1]}
                            )
                        if count == 2:
                            return snap.model_copy(
                                update={
                                    "binding": snap.binding.model_copy(
                                        update={"submission_key": "foreign-revision"}
                                    )
                                }
                            )
                        return snap

                    patch.setattr(c.deps.runs, "read", changed)
                    if fault == "journal-race":
                        expected = RevisionConflict
                with pytest.raises(expected):
                    bridge.verify(
                        wrong_plan,
                        wrong_d,
                        c.phases.closed.closure_refs,
                        wrong_op,
                        control,
                    )
            checked.append(fault)
            bridge.verify(plan, d, c.phases.closed.closure_refs, operation, control)
            return c.phases.close(plan, reset, operation, control)

        def restore(
            self,
            plan: TaskExecutionPlan,
            closed: ClosedTaskResources,
            operation: OperationContext,
            control: OperationControl,
        ) -> EvidenceRef:
            bridge.verify(plan, d, closed.closure_refs, operation, control)
            return c.phases.restore(plan, closed, operation, control)

    c.deps = replace(c.deps, finalization=Finalization())
    assert execute_task(c.plan, c.deps).evaluation.status == "failure"
    assert checked == [fault] and c.model.calls == c.browser.calls == 1
    attempt = c.deps.runs.read(c.plan.read_operation).project()[1][0]
    closing = next(e.operation for e in attempt.events if e.stage == "closing")
    with pytest.raises(OwnershipConflict):
        bridge.verify(c.plan, d, (), closing, c.deps.controls.bind(closing))


def test_stopped_run_and_expired_execution_read_allow_only_original_bounded_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = cleanup_case(tmp_path / "task")
    c, bridge, d = f.task, f.bridge, f.declaration
    c.phases.errors["capture"] = OperationStopped(
        "CANCELLED", c.plan.operation.operation_id
    )
    calls = []

    class Finalization:
        def close(
            self,
            plan: TaskExecutionPlan,
            reset: Any,
            operation: OperationContext,
            control: OperationControl,
        ) -> ClosedTaskResources:
            read = operation.model_copy(
                update={"operation_id": "unit-stopped-run-read", "attempt_id": None}
            )
            snap = c.deps.runs.read(read)
            run = snap.project()[0]
            closing = read.model_copy(update={"operation_id": "unit-original-run-stop"})
            entry = RunEntry(
                event=RunEvent(
                    stage="closing",
                    operation=closing,
                    previous_operation_id=run.events[-1].operation.operation_id,
                    occurred_at=c.deps.clock.utcnow(),
                    component_id="unit-stopped-run",
                    outputs=(plan.reset_plan_ref,),
                    stop_reason="cancelled",
                )
            )
            c.deps.runs.append(entry, snap.revision, closing)
            original = c.deps.runs.read

            def no_execute_read(op: OperationContext) -> Any:
                if op == plan.read_operation:
                    raise OperationStopped("DEADLINE_EXCEEDED", op.operation_id)
                return original(op)

            monkeypatch.setattr(c.deps.runs, "read", no_execute_read)
            bridge.verify(plan, d, c.phases.closed.closure_refs, operation, control)
            calls.append("closed")
            return c.phases.close(plan, reset, operation, control)

        def restore(
            self,
            plan: TaskExecutionPlan,
            closed: ClosedTaskResources,
            operation: OperationContext,
            control: OperationControl,
        ) -> EvidenceRef:
            bridge.verify(plan, d, closed.closure_refs, operation, control)
            calls.append("restored")
            return c.phases.restore(plan, closed, operation, control)

    c.deps = replace(c.deps, finalization=Finalization())
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    assert isinstance(caught.value.primary, OperationStopped)
    assert calls == ["closed", "restored"]
    assert "reset" in caught.value.known


def test_only_exact_original_native_recovery_phases_fit_restoring_parent(
    tmp_path: Path,
) -> None:
    f = cleanup_case(tmp_path / "task")
    c, bridge, d = f.task, f.bridge, f.declaration
    checked = []

    class Finalization:
        def close(
            self,
            plan: TaskExecutionPlan,
            reset: Any,
            operation: OperationContext,
            control: OperationControl,
        ) -> ClosedTaskResources:
            bridge.verify(plan, d, c.phases.closed.closure_refs, operation, control)
            return c.phases.close(plan, reset, operation, control)

        def restore(
            self,
            plan: TaskExecutionPlan,
            closed: ClosedTaskResources,
            operation: OperationContext,
            control: OperationControl,
        ) -> EvidenceRef:
            bridge.verify(plan, d, closed.closure_refs, operation, control)
            reset = closed.reset_plan
            for identifier, parent, recovery in [
                (
                    d.restore_operation_id,
                    reset.parent_operation_id,
                    reset.task_recovery_ref,
                ),
                (
                    d.resume_operation_id,
                    d.restore_operation_id,
                    reset.environment_recovery_ref,
                ),
                (
                    d.qualification_operation_id,
                    reset.parent_operation_id,
                    reset.environment_recovery_ref,
                ),
                (
                    d.reset_operation_id,
                    reset.parent_operation_id,
                    reset.environment_recovery_ref,
                ),
            ]:
                leaf = operation.model_copy(
                    update={
                        "operation_id": identifier,
                        "parent_operation_id": parent,
                        "allocation_id": "held-original-unit-site",
                        "recovery_ref": recovery,
                    }
                )
                bridge.verify(plan, d, closed.closure_refs, leaf, control)
                checked.append(identifier)
            changes: list[dict[str, Any]] = [
                {"parent_operation_id": "foreign-restore"},
                {"allocation_id": "foreign-site"},
                {"recovery_ref": reset.task_recovery_ref},
                {"operation_id": "unregistered-native-phase"},
            ]
            for change in changes:
                wrong = leaf.model_copy(update=change)
                count = len(f.source.calls)
                with pytest.raises(OwnershipConflict):
                    bridge.verify(plan, d, closed.closure_refs, wrong, control)
                assert len(f.source.calls) == count
            return c.phases.restore(plan, closed, operation, control)

    c.deps = replace(c.deps, finalization=Finalization())
    assert execute_task(c.plan, c.deps).evaluation.status == "failure"
    assert checked == [
        d.restore_operation_id,
        d.resume_operation_id,
        d.qualification_operation_id,
        d.reset_operation_id,
    ]
