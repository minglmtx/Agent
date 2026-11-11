"""Private category native facts; no order fixture or public target projection."""

from typing import Literal
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.identity import TaskIdentity
from ..query_state import QueryProtectedState
from .navigation_spec import CategoryNavigationSpec


class CategoryNavigationExecutionInput(Contract):
    schema_version: Literal["shopping-category-execution/1"] = (
        "shopping-category-execution/1"
    )
    spec: CategoryNavigationSpec


class CategoryNavigationState(Contract):
    schema_version: Literal["shopping-category-state/1"] = "shopping-category-state/1"
    task: TaskIdentity
    protected: QueryProtectedState

    def check(self, spec: CategoryNavigationSpec) -> None:
        if self.task != spec.task:
            raise ValueError("Category state changed the original task identity")
