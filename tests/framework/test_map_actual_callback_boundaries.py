"""New actual callbacks reject invalid dispatch inputs before touching resources."""

from pathlib import Path
from actor_context_projection_fixtures import actor_projection_case
from typing import Any
import pytest
from map_actor_callbacks import MapActorCallbacks
from map_browser_capture_native import capture
from map_task_operations_native import execute


@pytest.mark.parametrize(
    "value", [None, "", 1, [], {}, "unknown", "map-native-reference"]
)
def test_invalid_browser_collector_has_no_resource_access(value: Any) -> None:
    missing: Any = None
    with pytest.raises(ValueError):
        capture(missing, missing, value)


@pytest.mark.parametrize("value", [None, "", 1, [], {}, "inspect", "retry"])
def test_invalid_lifecycle_action_has_no_resource_access(value: Any) -> None:
    missing: Any = None
    with pytest.raises(ValueError):
        execute(missing, value, None)


def test_wrong_source_is_retained_without_evaluation_or_capture(tmp_path: Path) -> None:
    missing: Any = None
    callbacks = MapActorCallbacks(
        missing,
        missing,
        missing,
        tmp_path,
        context_policy=actor_projection_case().policy,
    )
    with pytest.raises(TypeError):
        callbacks.collect(missing, missing, missing)
    facts: dict[str, Any] = {}
    callbacks.evaluate(missing, facts)
    assert len(callbacks.errors) == 1 and isinstance(callbacks.errors[0], TypeError)
    assert facts["actor"] is callbacks.facts and "judgment" not in callbacks.facts
