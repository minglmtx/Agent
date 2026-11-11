"""Selected product-description coverage; not arbitrary Admin task support."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from .product_preparation_checks import PRODUCT_PREPARATION_CHECKS
from .product_initial_observation import PRODUCT_INITIAL_CHECKS

from ..state_evidence import (
    ENVIRONMENT_CHECKS as ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS as ENVIRONMENT_RESET_CHECKS,
    HEALTH_CHECKS as HEALTH_CHECKS,
)

TASK_RESET_CHECKS = (
    "admin.product.absent",
    "admin.database.restored",
    "admin.artifacts.restored",
    "admin.cache.cleared",
    "admin.search.restored",
)


def product_initial_state_spec(task: TaskIdentity) -> InitialStateSpec:
    if (task.site, task.family, task.contract_version) != (
        "shopping_admin",
        "product_description",
        1,
    ):
        raise ValueError("Unsupported task for Admin product state qualification")
    return InitialStateSpec(
        spec_id="admin-product-state-v1",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=PRODUCT_PREPARATION_CHECKS,
        initial_checks=PRODUCT_INITIAL_CHECKS,
        equivalence_checks=("admin.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
