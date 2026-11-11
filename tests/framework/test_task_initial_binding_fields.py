"""Optional body handoff cannot replace any required original authority binding."""

from dataclasses import replace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.task_execution_bindings import TaskInitialBinding


@pytest.mark.parametrize(
    "field",
    [
        "declaration",
        "declaration_ref",
        "browser",
        "state",
        "context",
        "capture",
        "initial",
    ],
)
def test_missing_required_binding_still_refuses_even_with_optional_default(
    field: str,
) -> None:
    # Field presence only; these explicit markers are not runtime authority.
    marker: Any = object()
    complete = TaskInitialBinding(
        marker, marker, marker, marker, marker, marker, marker
    )
    assert complete.inputs is None and complete.complete()
    malformed: dict[str, Any] = {field: None}
    assert not replace(complete, **malformed).complete()


@pytest.mark.parametrize("value", [False, 1, "", {}, [], object()])
def test_invalid_optional_input_cannot_pass_required_binding_check(value: Any) -> None:
    marker: Any = object()
    assert not TaskInitialBinding(
        marker, marker, marker, marker, marker, marker, marker, value
    ).complete()
