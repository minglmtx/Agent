"""Original physical GitLab/environment coverage shared by explicit families."""

ENVIRONMENT_CHECKS = (
    "gitlab.instance.original",
    "gitlab.six_services.initial_ready",
    "gitlab.snapshot.complete",
    "gitlab.native.complete",
)
INITIAL_CHECKS = ("gitlab.initial.observation",)
TASK_RESET_CHECKS = ("gitlab.full_tree.restored", "gitlab.complete_native.restored")
ENVIRONMENT_RESET_CHECKS = ("gitlab.six_services.resumed",)
HEALTH_CHECKS = ("gitlab.backends.ready", "gitlab.frontend.ready")
