"""Preparation authority at real current run/construction stages; fake physical rights."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.application.construction_task_phases import (
    ConstructionTaskPreparationAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from task_execution_fixtures import TaskCase, task_case
from construction_storage_fixtures import put
from test_core_contracts import reference
from task_preparation_declaration_fixtures import preparation_declaration


def declaration(c: TaskCase) -> SiteTaskPreparationPlan:
    return preparation_declaration(
        c.plan,
        c.phases.closed.reset_plan,
        c.admission.data.plan.task,
        c.admission.data.store,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "foreign-attempt",
        "declaration-bytes",
        "unlinked-cleanup",
        "source-denied",
        "changed-journal",
    ],
)
def test_original_pending_attempt_admission_at_current_lifecycle_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = task_case(tmp_path / "task")
    d = declaration(c)
    c.plan = c.plan.model_copy(
        update={"declaration_ref": put(c.admission.data.store, d, d.schema_version)}
    )
    bridge = ConstructionTaskPreparationAuthority(
        c.deps.construction, c.deps.runs, c.phases, c.deps.evidence
    )
    admitted = []

    class Preparation:
        def acquire(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            if fault != "none":
                wrong_op, wrong_d = operation, d
                with monkeypatch.context() as patch:
                    expected: type[Exception] = OwnershipConflict
                    if fault == "foreign-attempt":
                        wrong_op = operation.model_copy(
                            update={"attempt_id": "foreign-attempt"}
                        )
                    elif fault == "declaration-bytes":
                        wrong_d = d.model_copy(
                            update={"snapshot_schema": "unit-foreign-snapshot/1"}
                        )
                    elif fault == "unlinked-cleanup":
                        wrong_op = operation.cleanup(
                            "unit-unlinked-read",
                            now=datetime.now(timezone.utc),
                            seconds=30,
                        )
                    elif fault == "source-denied":
                        patch.setattr(c.phases, "denied", True)
                        expected = PermissionError
                    else:
                        original_read = c.deps.runs.read
                        count = 0

                        def changed(op: OperationContext) -> Any:
                            nonlocal count
                            count += 1
                            value = original_read(op)
                            if count == 2:
                                return value.model_copy(
                                    update={
                                        "binding": value.binding.model_copy(
                                            update={
                                                "submission_key": "changed-observed-journal"
                                            }
                                        )
                                    }
                                )
                            return value

                        patch.setattr(c.deps.runs, "read", changed)
                        expected = RevisionConflict
                    with pytest.raises(expected):
                        bridge.verify(plan, wrong_d, wrong_op, control)
                assert c.model.calls == c.browser.calls == 0
            bridge.verify(plan, d, operation, control)
            admitted.append("acquiring")
            return c.phases.acquire(plan, operation, control)

        def prepare(
            self,
            plan: TaskExecutionPlan,
            operation: OperationContext,
            control: OperationControl,
        ) -> tuple[EvidenceRef, ...]:
            bridge.verify(plan, d, operation, control)
            admitted.append("preparing")
            return c.phases.prepare(plan, operation, control)

    with pytest.raises(OwnershipConflict, match="live pending attempt"):
        bridge.verify(
            c.plan, d, c.plan.operation, c.deps.controls.bind(c.plan.operation)
        )
    c.deps = replace(c.deps, preparation=Preparation())
    result = execute_task(c.plan, c.deps)
    assert result.evaluation.status == "failure"
    assert admitted == ["acquiring", "preparing"]
    assert c.model.calls == c.browser.calls == 1
    with pytest.raises(OwnershipConflict, match="acquiring/preparing"):
        bridge.verify(
            c.plan, d, c.plan.operation, c.deps.controls.bind(c.plan.operation)
        )


def test_original_journals_and_physical_authority_are_mandatory() -> None:
    missing: Any = None
    with pytest.raises(ValueError, match="mandatory"):
        ConstructionTaskPreparationAuthority(missing, missing, missing, missing)
