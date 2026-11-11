"""No owner or source may be inferred by the new site composition function.

These refusals are only boundary checks; full Admin default execution and actual
resource/source qualification need their own original evidence.
"""

from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_navigation_task_execution import (
    admin_navigation_task_execution,
)


@pytest.mark.parametrize("value", [None, {}, [], "", True, 1])
def test_explicit_original_typed_admin_dependencies_are_required(value: Any) -> None:
    with pytest.raises(TypeError):
        admin_navigation_task_execution(value, value, value, value)
