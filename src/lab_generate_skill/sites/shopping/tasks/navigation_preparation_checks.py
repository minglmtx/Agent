"""Original category preparation, including same-call checked body handoff."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from ..state_reads import ShoppingStateReads
from .navigation_admission import task_input, same_snapshot
from .navigation_policy import category_navigation_initial_spec, PREPARATION_CHECKS
from .navigation_recovery import CategoryNavigationRecoverySnapshot
from .navigation_spec import CategoryNavigationSpec, CategoryNavigationInputs
from .navigation_state import CategoryNavigationState


class CategoryNavigationPreparationChecks(ShoppingStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        return self.check_with_bodies(inputs, None, None, control)

    def check_with_bodies(
        self,
        inputs: PreparationInputs,
        private_spec: bytes | None,
        snapshot: bytes | None,
        control: OperationControl,
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        control.checkpoint()
        request = inputs.request
        data = task_input(request)
        if inputs.spec != category_navigation_initial_spec(request.task) or (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
        ) != ("shopping-category-navigation", "1"):
            raise OwnershipConflict(
                "Category preparation changed full declared policy/recovery"
            )
        if request.snapshot_ref is None:
            raise OwnershipConflict("Original category snapshot reference required")
        for reference, schema in (
            (inputs.binding.private_spec_ref, "shopping-category-navigation/1"),
            (request.snapshot_ref, "shopping-category-recovery/1"),
        ):
            private_state_ref(reference, schema)
            if reference.media_type != "application/json":
                raise ValueError("Original category private JSON required")
        if private_spec is None:
            private = self.read(
                inputs.binding.private_spec_ref,
                "shopping-category-navigation/1",
                CategoryNavigationSpec,
                control,
            )
        else:
            require_complete_bytes(inputs.binding.private_spec_ref, private_spec)
            private = CategoryNavigationSpec.model_validate_json(private_spec)
            if private.model_dump_json().encode() != private_spec:
                raise ValueError("Noncanonical original category private input")
        if private != data.spec:
            raise OwnershipConflict(
                "Category preparation changed original private binding"
            )
        CategoryNavigationInputs(public_task=inputs.public_task, private_spec=private)
        if snapshot is None:
            saved = self.read(
                request.snapshot_ref,
                "shopping-category-recovery/1",
                CategoryNavigationRecoverySnapshot,
                control,
            )
        else:
            require_complete_bytes(request.snapshot_ref, snapshot)
            saved = CategoryNavigationRecoverySnapshot.model_validate_json(snapshot)
            if saved.model_dump_json().encode() != snapshot:
                raise ValueError("Noncanonical original category snapshot")
        same_snapshot(request, saved, request.snapshot_ref)
        observed = CategoryNavigationState.model_validate_json(
            inputs.result.private_result
        )
        if (
            inputs.result.request_sha256 != request.digest
            or request.action != "prepare"
            or observed.model_dump_json() != inputs.result.private_result
            or observed.task != request.task
            or observed.protected != saved.protected
            or saved.state.service.files.instance_id
            != inputs.environment.allocation.expected_resource_id
        ):
            raise OwnershipConflict(
                "Category preparation changed original measured native state"
            )
        control.checkpoint()
        return self.checks(
            PREPARATION_CHECKS,
            (
                inputs.selection.request_ref,
                inputs.selection.result_ref,
                request.snapshot_ref,
                inputs.binding.private_spec_ref,
            ),
            "ORIGINAL_CATEGORY_NATIVE_PREPARED",
        )
