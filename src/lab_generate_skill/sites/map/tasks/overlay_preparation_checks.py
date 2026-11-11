"""Original unchanged Map preparation; separate from environment/initial/reset gates."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import MapStateReads
from .overlay_spec import NativeOverlaySpec, NativeOverlayInputs
from .overlay_admission import task_input
from .overlay_policy import overlay_initial_spec, PREPARATION_CHECKS


class OverlayPreparationChecks(MapStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        request = inputs.request
        spec = task_input(request)
        if inputs.spec != overlay_initial_spec(request.task) or (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
            inputs.recovery.baseline_ref,
        ) != ("map-native-overlay", "1", inputs.binding.baseline_ref):
            raise OwnershipConflict(
                "Original selected Map preparation/recovery coverage required"
            )
        private = self.read(
            inputs.binding.private_spec_ref,
            "map-native-overlay/1",
            NativeOverlaySpec,
            control,
        )
        if private != spec:
            raise OwnershipConflict("Map preparation changed original private binding")
        NativeOverlayInputs(public_task=inputs.public_task, private_spec=private)
        observed = self.prepared(inputs.result, request, control)
        if (
            observed.native.plan.token != inputs.environment.allocation
            or observed.native.plan.scope != inputs.environment.scope
            or (
                observed.snapshot.native.state_sha256
                != inputs.environment.measured_state_sha256
            )
        ):
            raise OwnershipConflict(
                "Map preparation changed original measured environment"
            )
        assert request.snapshot_ref is not None
        refs = (
            inputs.selection.request_ref,
            inputs.selection.result_ref,
            request.snapshot_ref,
            inputs.binding.private_spec_ref,
            inputs.selection.environment_ref,
        )
        return StateChecks(
            required=PREPARATION_CHECKS,
            checks=tuple(
                CheckResult(
                    name=name,
                    status="pass",
                    reason_code="ORIGINAL_MAP_NATIVE_PREPARED",
                    evidence=refs,
                )
                for name in PREPARATION_CHECKS
            ),
        )
