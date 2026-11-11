"""Product-specific original schemas, policy and absence proof over shared state."""

from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_evidence import AdminStateChecks, AdminRecoveryView, AdminRestoredView
from .product_recovery_contract import ProductRecoverySnapshot, ProductRestored
from .product_state_policy import product_initial_state_spec, TASK_RESET_CHECKS


class ProductStateChecks(AdminStateChecks):
    task_reset_checks = TASK_RESET_CHECKS
    restore_component = ("admin-product", "3")

    def specification(self, task: TaskIdentity) -> InitialStateSpec:
        return product_initial_state_spec(task)

    def snapshot(
        self, reference: EvidenceRef, control: OperationControl
    ) -> AdminRecoveryView:
        original = self.read(
            reference, "admin-product-recovery/2", ProductRecoverySnapshot, control
        )
        return AdminRecoveryView(original.request, original.state, original.product)

    def restored(self, raw: str) -> AdminRestoredView:
        original = ProductRestored.model_validate_json(raw)
        return AdminRestoredView(
            original.task,
            original.operation,
            original.snapshot_ref,
            original.state,
            original.frontend,
            original.product,
        )
