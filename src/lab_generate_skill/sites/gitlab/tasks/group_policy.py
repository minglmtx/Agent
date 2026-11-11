"""Current Group initial-state coverage; declarations never grant execution."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from ..state_policy import (
    ENVIRONMENT_CHECKS as ENVIRONMENT_CHECKS,
    INITIAL_CHECKS as INITIAL_CHECKS,
    TASK_RESET_CHECKS as TASK_RESET_CHECKS,
    ENVIRONMENT_RESET_CHECKS as ENVIRONMENT_RESET_CHECKS,
    HEALTH_CHECKS as HEALTH_CHECKS,
)

PREPARATION_CHECKS = (
    "gitlab.group.original_spec",
    "gitlab.group.original_snapshot",
    "gitlab.group.native_unchanged",
)


def group_initial_spec(task: TaskIdentity) -> InitialStateSpec:
    task = TaskIdentity.model_validate(task)
    if (task.site, task.family, task.contract_version, task.split) != (
        "gitlab",
        "group_creation",
        1,
        "train",
    ):
        raise ValueError("Unsupported selected Group initial-state family")
    return InitialStateSpec(
        spec_id="gitlab-group-creation-state-v1",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=INITIAL_CHECKS,
        equivalence_checks=("gitlab.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
