"""Navigation preparation joins original binding and complete unchanged native state."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import MapStateReads
from ..preparation_bodies import MapPreparationBodies
from .navigation_admission import task_input
from .navigation_spec import NavigationSpec, NavigationInputs
from .navigation_policy import navigation_initial_spec, PREPARATION_CHECKS


class NavigationPreparationChecks(MapStateReads):
    def check_with_bodies(
        self,
        inputs: PreparationInputs,
        private_spec: bytes | None,
        snapshot: bytes | None,
        control: OperationControl,
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        control.checkpoint()
        reader = MapPreparationBodies(self.store, inputs, private_spec, snapshot)
        return NavigationPreparationChecks(reader, self.files).check(inputs, control)

    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        request = inputs.request
        spec = task_input(request)
        if inputs.spec != navigation_initial_spec(
            request.task, spec.native_contract_ref.sha256
        ) or (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
            inputs.recovery.baseline_ref,
        ) != (
            "map-native-navigation",
            "1",
            inputs.binding.baseline_ref,
        ):
            raise OwnershipConflict(
                "Exact navigation preparation/recovery coverage required"
            )
        private = self.read(
            inputs.binding.private_spec_ref,
            "map-navigation-spec/1",
            NavigationSpec,
            control,
        )
        if private != spec:
            raise OwnershipConflict(
                "Navigation preparation changed original private binding"
            )
        NavigationInputs(public_task=inputs.public_task, private_spec=private)
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
                "Navigation preparation changed original measured environment"
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
                    reason_code="ORIGINAL_MAP_NAVIGATION_PREPARED",
                    evidence=refs,
                )
                for name in PREPARATION_CHECKS
            ),
        )
