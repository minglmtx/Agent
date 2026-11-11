"""Recompute original private fixture/preparation from immutable returned facts."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import ShoppingStateReads
from .order_eta_policy import order_eta_initial_spec, PREPARATION_CHECKS
from .order_eta_admission import task_input, same_snapshot
from .order_eta_recovery import OrderEtaRecoverySnapshot
from .order_eta_state import OrderEtaState
from .order_eta_spec import OrderEtaSpec
from .order_eta_validation import validate_eta_initialization


class OrderEtaPreparationChecks(ShoppingStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        data, request = task_input(inputs.request), inputs.request
        if inputs.spec != order_eta_initial_spec(request.task):
            raise ValueError("Unsupported Shopping preparation coverage")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
        ) != ("shopping-order-eta", "1"):
            raise ValueError("Unsupported original Shopping task recovery")
        private = self.read(
            inputs.binding.private_spec_ref,
            "shopping-recorded-order-eta/1",
            OrderEtaSpec,
            control,
        )
        if private != data.spec or request.snapshot_ref is None:
            raise OwnershipConflict(
                "Shopping preparation changed original private input/snapshot"
            )
        snapshot = self.read(
            request.snapshot_ref,
            "shopping-eta-recovery/1",
            OrderEtaRecoverySnapshot,
            control,
        )
        same_snapshot(request, snapshot, request.snapshot_ref)
        if (
            snapshot.state.service.files.instance_id
            != inputs.environment.allocation.expected_resource_id
        ):
            raise OwnershipConflict(
                "Shopping snapshot changed original environment instance"
            )
        measured = OrderEtaState.model_validate_json(inputs.result.private_result)
        if measured.model_dump_json() != inputs.result.private_result:
            raise ValueError("Noncanonical original Shopping preparation measurement")
        validate_eta_initialization(data.spec, snapshot.protected, measured)
        control.checkpoint()
        return self.checks(
            PREPARATION_CHECKS,
            (
                inputs.selection.request_ref,
                inputs.selection.result_ref,
                request.snapshot_ref,
                inputs.binding.private_spec_ref,
            ),
            "ORIGINAL_NATIVE_ETA_PREPARED",
        )
