"""Explicit metadata deadline through the original Actor2/capture/close path.

Physical worker close limits and legacy capture bytes remain unchanged.
"""

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
import lab_generate_skill.domain.task_capture as schema
from lab_generate_skill.domain.task_capture import TaskCapturePlan
import task_capture_port_fixtures as fixture
from task_initialization_port_fixtures import initialization_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@contextmanager
def metadata_case(root: Path, patch: pytest.MonkeyPatch) -> Iterator[Any]:
    initialize = initialization_case

    @contextmanager
    def selected(*args: Any, **kwargs: Any) -> Iterator[Any]:
        freeze = kwargs["freeze_run"]
        kwargs["freeze_run"] = lambda p: freeze(p).model_copy(
            update={"cleanup_seconds": 1800}
        )
        with initialize(*args, **kwargs) as case:
            yield case

    def declaration(**kwargs: Any) -> TaskCapturePlan:
        return TaskCapturePlan(
            **{
                **kwargs,
                "schema_version": "task-capture-plan/2",
                "close_seconds": 60,
                "metadata_close_seconds": 1800,
            }
        )

    patch.setattr(fixture, "initialization_case", selected)
    patch.setattr(fixture, "TaskCapturePlan", declaration)
    with fixture.capture_case(root, patch) as case:
        yield case


def test_original_actor2_capture_close_and_guard_receive_explicit_metadata_budget(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with metadata_case(node_path, monkeypatch) as case:
        case.actor()
        clock = case.initial.preparation.original.resource.clock
        before = clock.utcnow()
        result = case.collect()
        d = case.capture.declaration
        closes = [
            op for op in case.authority.calls if op.operation_id == d.close_operation_id
        ]
        assert closes and all(
            (op.deadline - before).total_seconds() > 1700 for op in closes
        )
        assert d.close_seconds == 60 and d.metadata_close_seconds == 1800
        assert case.initial.browser.phase == "closed" and case.site_authority.calls == 1
        assert result.contract == case.capture.plan.evaluation


def test_legacy_wire_is_identical_to_original_frozen_definition(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1/deployment-4895473/installation/runtime/lib/python3.11/site-packages/lab_generate_skill/domain/task_capture.py"
    )
    tree = ast.parse(original.read_text())
    old = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "TaskCapturePlan"
    )
    namespace = vars(schema).copy()
    exec(
        compile(ast.Module(body=[old], type_ignores=[]), str(original), "exec"),
        namespace,
    )
    with fixture.capture_case(node_path, monkeypatch) as case:
        d = case.capture.declaration
        raw = d.model_dump_json()
        assert "metadata_close_seconds" not in raw
        assert (
            namespace["TaskCapturePlan"].model_validate_json(raw).model_dump_json()
            == raw
        )


@pytest.mark.parametrize(
    "version,budget",
    [
        ("task-capture-plan/1", None),
        ("task-capture-plan/1", 1800),
        ("task-capture-plan/2", None),
        ("task-capture-plan/2", 0),
        ("task-capture-plan/2", 59),
        ("task-capture-plan/2", 3601),
        ("task-capture-plan/2", True),
        ("task-capture-plan/2", []),
        ("task-capture-plan/2", ""),
    ],
)
def test_wrong_version_missing_illegal_or_wrong_type_budget_refused(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, version: str, budget: Any
) -> None:
    with fixture.capture_case(node_path, monkeypatch) as case:
        raw = case.capture.declaration.model_dump()
        raw.update(
            schema_version=version, close_seconds=60, metadata_close_seconds=budget
        )
        with pytest.raises(ValidationError):
            TaskCapturePlan.model_validate(raw)


@pytest.mark.parametrize("close,budget", [(1, 1), (60, 60), (60, 3600)])
def test_explicit_metadata_budget_accepts_exact_declared_bounds(
    close: int, budget: int
) -> None:
    from test_task_capture_contracts import declaration

    raw = declaration().model_dump()
    raw.update(
        schema_version="task-capture-plan/2",
        close_seconds=close,
        metadata_close_seconds=budget,
    )
    selected = TaskCapturePlan.model_validate(raw)
    assert selected.close_seconds == close and selected.metadata_close_seconds == budget
    assert TaskCapturePlan.model_validate_json(selected.model_dump_json()) == selected
