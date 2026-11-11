"""Selected recorded-order task's required coverage, without execution rights."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec

ENVIRONMENT_CHECKS = (
    "shopping.instance.original",
    "shopping.services.initial_ready",
    "shopping.snapshot.complete",
)
PREPARATION_CHECKS = (
    "shopping.order.native_fixture",
    "shopping.order.original_snapshot",
    "shopping.protection.initialization",
)
INITIAL_CHECKS = ("shopping.initial.observation",)
TASK_RESET_CHECKS = (
    "shopping.full_state.restored",
    "shopping.native.original",
    "shopping.local_mail.original",
)
ENVIRONMENT_RESET_CHECKS = ("shopping.services.resumed",)
HEALTH_CHECKS = ("shopping.backends.ready", "shopping.frontend.ready")


def order_eta_initial_spec(task: TaskIdentity) -> InitialStateSpec:
    if (task.site, task.family, task.contract_version, task.split) != (
        "shopping",
        "recorded_order_eta",
        1,
        "train",
    ):
        raise ValueError("Unsupported selected Shopping initial-state family")
    return InitialStateSpec(
        spec_id="shopping-order-eta-state-v1",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=INITIAL_CHECKS,
        equivalence_checks=("shopping.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
