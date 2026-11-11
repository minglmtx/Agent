"""Existing construction admission is one explicit source of the shared lifecycle."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.construction_task_admission import (
    ConstructionTaskAdmission,
)
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from task_execution_fixtures import task_case
from test_slurm_commands import guard


def test_current_source_view_is_readonly_and_same_real_task_lifecycle_is_used(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "source")
    source = c.deps.source
    assert isinstance(source, ConstructionTaskAdmission) and source.deps is c.deps
    snapshot = c.deps.runs.read(c.plan.read_operation)
    state = source.open(c.plan, snapshot, guard())
    assert (
        state.source_kind == "construction" and state.binding == c.plan.intent.binding
    )
    source.verify_current(c.plan, state, snapshot, c.plan.operation)
    assert c.model.calls == c.browser.calls == 0 and c.phases.calls == []
    result = execute_task(c.plan, c.deps)
    assert (
        result.evaluation.status == "failure" and c.model.calls == c.browser.calls == 1
    )
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.model.calls == c.browser.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [("source_kind", "execution"), ("max_generations", 1), ("max_interactions", 1)],
)
def test_source_view_cannot_relabel_or_change_original_limits(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    c = task_case(tmp_path / field)
    snapshot = c.deps.runs.read(c.plan.read_operation)
    state = c.deps.source.open(c.plan, snapshot, guard())
    changed_value = (
        value if field == "source_kind" else getattr(state, field) % 10000 + 1
    )
    changed = state.model_copy(update={field: changed_value})
    with pytest.raises(OwnershipConflict):
        c.deps.source.verify_current(c.plan, changed, snapshot, c.plan.operation)
    assert c.model.calls == c.browser.calls == 0 and c.phases.calls == []
    assert c.deps.runs.read(c.plan.read_operation) == snapshot


def test_dataclass_rebind_rebuilds_source_on_exact_new_dependencies(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "copy")
    other = replace(c.deps, admission=replace(c.deps.admission))
    assert isinstance(other.source, ConstructionTaskAdmission)
    assert other.source is not c.deps.source and other.source.deps is other
    assert other.construction is c.deps.construction and other.runs is c.deps.runs
    assert other.source.original is None


@pytest.mark.parametrize("value", [None, {}, [], "", False, 1])
def test_missing_or_invalid_task_admission_view_is_not_a_grant(
    tmp_path: Path, value: Any
) -> None:
    c = task_case(tmp_path / "unopened")
    snapshot = c.deps.runs.read(c.plan.read_operation)
    with pytest.raises(OwnershipConflict):
        c.deps.source.verify_current(c.plan, value, snapshot, c.plan.operation)
    assert c.model.calls == c.browser.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_kind", "other"),
        ("max_generations", False),
        ("max_interactions", 0),
        ("max_generations", 10001),
    ],
)
def test_admission_state_rejects_unknown_modes_and_illegal_limits(
    tmp_path: Path, field: str, value: Any
) -> None:
    c = task_case(tmp_path / "invalid")
    snapshot = c.deps.runs.read(c.plan.read_operation)
    state = c.deps.source.open(c.plan, snapshot, guard())
    raw = state.model_dump(mode="json")
    raw[field] = value
    import json

    with pytest.raises(ValueError):
        TaskAdmissionState.model_validate_json(json.dumps(raw))
    assert c.model.calls == c.browser.calls == 0
