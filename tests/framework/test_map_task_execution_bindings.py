"""Map default assembly imports/typed boundary; no inferred rights or resources."""

from typing import Any
import pytest
from lab_generate_skill.bootstrap.map_task_execution import (
    map_navigation_task_execution,
)


@pytest.mark.parametrize("bad", [None, {}, [], True, "missing", 1])
def test_map_default_requires_explicit_typed_original_inputs(bad: Any) -> None:
    with pytest.raises(TypeError):
        map_navigation_task_execution(bad, bad, bad, bad)
