"""Required coverage of this selected train consumer, without execution rights."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec

ENVIRONMENT_CHECKS = (
    "reddit.instance.original",
    "reddit.three_services.initial_ready",
    "reddit.snapshot.complete",
    "reddit.native.complete",
)
PREPARATION_CHECKS = (
    "reddit.image.original_spec",
    "reddit.image.original_snapshot",
    "reddit.image.native_unchanged",
)
INITIAL_CHECKS = ("reddit.initial.observation",)
TASK_RESET_CHECKS = ("reddit.full_tree.restored", "reddit.complete_native.restored")
ENVIRONMENT_RESET_CHECKS = ("reddit.three_services.resumed",)
HEALTH_CHECKS = ("reddit.backends.ready", "reddit.frontend.ready")


def image_initial_spec(task: TaskIdentity) -> InitialStateSpec:
    if (task.site, task.family, task.contract_version, task.split) != (
        "reddit",
        "native_image_submission",
        1,
        "train",
    ):
        raise ValueError("Unsupported selected Reddit initial-state family")
    return InitialStateSpec(
        spec_id="reddit-native-image-state-v1",
        task=task,
        environment_checks=ENVIRONMENT_CHECKS,
        preparation_checks=PREPARATION_CHECKS,
        initial_checks=INITIAL_CHECKS,
        equivalence_checks=("reddit.initial.equivalence",),
        task_reset_checks=TASK_RESET_CHECKS,
        environment_reset_checks=ENVIRONMENT_RESET_CHECKS,
        health_checks=HEALTH_CHECKS,
    )
