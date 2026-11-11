"""Reconstruct Group read-only preparation from full original native bytes."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .group_reads import GroupStateReads
from .group_spec import GroupSpec
from .group_request import task_input
from .group_recovery import GroupRecoverySnapshot, GroupObserved
from .native_snapshot import same_native_snapshot
from .group_capture import same_group_state
from .group_rules import validate_group_initial
from .group_policy import group_initial_spec, PREPARATION_CHECKS


class GroupPreparationChecks(GroupStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        request = inputs.request
        spec = task_input(request)
        if inputs.spec != group_initial_spec(request.task):
            raise ValueError("Unsupported Group preparation coverage")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
            inputs.recovery.baseline_ref,
        ) != ("gitlab-group-creation", "1", inputs.binding.baseline_ref):
            raise ValueError("Unsupported original Group recovery")
        private = self.read(
            inputs.binding.private_spec_ref,
            "gitlab-group-creation/1",
            GroupSpec,
            control,
        )
        if private != spec or request.snapshot_ref is None:
            raise OwnershipConflict("Group preparation changed bound input/snapshot")
        snapshot = self.read(
            request.snapshot_ref,
            "gitlab-group-recovery/1",
            GroupRecoverySnapshot,
            control,
        )
        same_native_snapshot(
            request,
            snapshot.request,
            snapshot.model_dump_json().encode(),
            snapshot.schema_version,
            request.snapshot_ref,
            "Group",
        )
        context = snapshot.native_before.context
        if (
            context.token != inputs.environment.allocation
            or context.instance.files != snapshot.state.service.files
        ):
            raise OwnershipConflict(
                "Group preparation changed original environment allocation"
            )
        observed = GroupObserved.model_validate_json(inputs.result.private_result)
        if (
            observed.model_dump_json() != inputs.result.private_result
            or observed.request != request
            or observed.snapshot != snapshot
        ):
            raise OwnershipConflict("Original Group preparation measurement changed")
        before = self.native(snapshot.native_before, snapshot.request, control)
        current = self.native(observed.native, request, control)
        validate_group_initial(spec, before.state)
        if not same_group_state(before, current):
            raise OwnershipConflict(
                "Read-only Group preparation changed original complete native state"
            )
        return self.checks(
            PREPARATION_CHECKS,
            (
                inputs.selection.request_ref,
                inputs.selection.result_ref,
                request.snapshot_ref,
                inputs.binding.private_spec_ref,
                snapshot.native_before.payload_ref,
                observed.native.payload_ref,
            ),
            "ORIGINAL_GROUP_NATIVE_PREPARED",
        )
