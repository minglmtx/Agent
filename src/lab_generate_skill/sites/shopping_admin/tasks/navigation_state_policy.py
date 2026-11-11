"""Selected navigation coverage; no product creation/absence is inferred."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from ..state_evidence import (
    ENVIRONMENT_CHECKS as ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS as ENVIRONMENT_RESET_CHECKS,
    HEALTH_CHECKS as HEALTH_CHECKS,
)
from .navigation_preparation_checks import NAVIGATION_PREPARATION_CHECKS
from .navigation_initial_observation import NAVIGATION_INITIAL_CHECKS

TASK_RESET_CHECKS = (
    "admin.database.restored",
    "admin.artifacts.restored",
    "admin.cache.cleared",
    "admin.search.restored",
)


def navigation_initial_state_spec(task: TaskIdentity) -> InitialStateSpec:
    if (task.site, task.family, task.contract_version, task.split) != (
        "shopping_admin",
        "page_navigation",
        1,
        "train",
    ):
        raise ValueError("Unsupported task for Admin navigation state qualification")
    return InitialStateSpec(
        spec_id="admin-navigation-state-v2-held-search",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=NAVIGATION_PREPARATION_CHECKS,
        initial_checks=NAVIGATION_INITIAL_CHECKS,
        equivalence_checks=("admin.navigation.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
