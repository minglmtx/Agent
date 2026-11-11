"""Category coverage over original complete Shopping protection and recovery."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from .order_eta_policy import (
    ENVIRONMENT_CHECKS,
    TASK_RESET_CHECKS,
    ENVIRONMENT_RESET_CHECKS,
    HEALTH_CHECKS,
)

PREPARATION_CHECKS = (
    "shopping.category.original_snapshot",
    "shopping.category.native_unchanged",
)


def category_navigation_initial_spec(task: TaskIdentity) -> InitialStateSpec:
    if (task.site, task.family, task.contract_version, task.split) != (
        "shopping",
        "page_navigation",
        1,
        "train",
    ):
        raise ValueError("Unsupported Shopping category initial-state family")
    return InitialStateSpec(
        spec_id="shopping-category-navigation-state-v1",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=("shopping.initial.observation",),
        equivalence_checks=("shopping.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
