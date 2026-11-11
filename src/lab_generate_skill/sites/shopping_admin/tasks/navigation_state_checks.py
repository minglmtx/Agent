"""Navigation-specific original schemas, policy and declared scope over shared state."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_evidence import AdminStateChecks, AdminRecoveryView, AdminRestoredView
from .navigation_recovery_contract import NavigationRecoverySnapshot, NavigationRestored
from .navigation_state_policy import navigation_initial_state_spec, TASK_RESET_CHECKS


class NavigationStateChecks(AdminStateChecks):
    task_reset_checks = TASK_RESET_CHECKS
    restore_component = ("admin-navigation", "1")

    def specification(self, task: TaskIdentity) -> InitialStateSpec:
        return navigation_initial_state_spec(task)

    def snapshot(
        self, reference: EvidenceRef, control: OperationControl
    ) -> AdminRecoveryView:
        original = self.read(
            reference,
            "admin-navigation-recovery/1",
            NavigationRecoverySnapshot,
            control,
        )
        return AdminRecoveryView(original.request, original.state, None)

    def restored(self, raw: str) -> AdminRestoredView:
        original = NavigationRestored.model_validate_json(raw)
        return AdminRestoredView(
            original.task,
            original.operation,
            original.snapshot_ref,
            original.state,
            original.frontend,
            None,
        )
