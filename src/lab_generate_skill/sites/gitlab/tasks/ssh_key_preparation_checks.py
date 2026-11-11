"""Reconstruct original SSH no-op preparation from full native private evidence."""

from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import GitlabStateReads
from .ssh_key_spec import SshKeySpec
from .ssh_key_admission import task_input, same_snapshot
from .ssh_key_recovery import SshKeyRecoverySnapshot, SshKeyObserved
from .ssh_key_rules import preserved
from .ssh_key_policy import ssh_key_initial_spec, PREPARATION_CHECKS


class SshKeyPreparationChecks(GitlabStateReads):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        inputs = PreparationInputs.model_validate(inputs)
        request = inputs.request
        spec = task_input(request)
        if inputs.spec != ssh_key_initial_spec(request.task):
            raise ValueError("Unsupported GitLab preparation coverage")
        if (
            inputs.recovery.restore_component_id,
            inputs.recovery.restore_component_version,
            inputs.recovery.baseline_ref,
        ) != ("gitlab-profile-ssh-key", "1", inputs.binding.baseline_ref):
            raise ValueError("Unsupported original SSH-key recovery")
        private = self.read(
            inputs.binding.private_spec_ref,
            "gitlab-profile-ssh-key/1",
            SshKeySpec,
            control,
        )
        if private != spec or request.snapshot_ref is None:
            raise OwnershipConflict(
                "GitLab preparation changed bound private input/snapshot"
            )
        snapshot = self.read(
            request.snapshot_ref,
            "gitlab-ssh-key-recovery/1",
            SshKeyRecoverySnapshot,
            control,
        )
        same_snapshot(request, snapshot, request.snapshot_ref)
        context = snapshot.native_before.context
        if (
            context.token != inputs.environment.allocation
            or context.instance.files != snapshot.state.service.files
        ):
            raise OwnershipConflict(
                "SSH-key preparation changed original environment allocation"
            )
        observed = SshKeyObserved.model_validate_json(inputs.result.private_result)
        if (
            observed.model_dump_json() != inputs.result.private_result
            or observed.request != request
            or observed.snapshot != snapshot
        ):
            raise OwnershipConflict("Original SSH-key preparation measurement changed")
        before = self.native(snapshot.native_before, snapshot.request, control)
        current = self.native(observed.native, request, control)
        if not preserved(before, current) or before.keys != current.keys:
            raise OwnershipConflict(
                "SSH-key preparation changed complete original native state"
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
            "ORIGINAL_SSH_NATIVE_PREPARED",
        )
