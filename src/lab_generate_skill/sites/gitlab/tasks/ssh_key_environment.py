"""Original six-service/full-native environment semantics, without launch rights."""

import hashlib
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import GitlabStateReads
from ..environment_identity import original_environment, original_environment_recovery
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from .ssh_key_spec import SshKeySpec
from .ssh_key_admission import task_input
from .ssh_key_recovery import SshKeyRecoverySnapshot
from .ssh_key_policy import (
    ssh_key_initial_spec,
    GITLAB_IMAGE_SHA,
    ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS,
)


class SshKeyEnvironmentChecks(GitlabStateReads):
    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> tuple[InitialStateSpec, SiteResourceSpec, SshKeyRecoverySnapshot]:
        selection = EnvironmentSelection.model_validate(selection)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        if spec != ssh_key_initial_spec(selection.scope.task):
            raise ValueError("Unsupported or incomplete SSH initial-state coverage")
        site = self.read(
            selection.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
        )
        started = self.read(
            selection.site_started_ref,
            "site-resource-started/1",
            SiteResourceStarted,
            control,
        )
        snapshot = self.read(
            selection.snapshot_ref,
            "gitlab-ssh-key-recovery/1",
            SshKeyRecoverySnapshot,
            control,
        )
        request, config, scope = snapshot.request, site.configuration, selection.scope
        request.check_site(config)
        private = task_input(request)
        if (site.token.owner, request.task, request.operation.attempt_id) != (
            scope.owner,
            scope.task,
            scope.attempt_id,
        ):
            raise OwnershipConflict("SSH environment changed original scope")
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        bound = self.read(
            binding.private_spec_ref, "gitlab-profile-ssh-key/1", SshKeySpec, control
        )
        if (binding.identity, binding.baseline_ref, bound) != (
            scope.task,
            selection.spec_ref,
            private,
        ):
            raise OwnershipConflict(
                "SSH environment changed original private binding/spec"
            )
        original_environment(
            site,
            started,
            snapshot.state,
            snapshot.native_before.context,
            GITLAB_PRIVATE_JSON,
            "SSH",
        )
        self.native(snapshot.native_before, request, control)
        recovery = self.read(
            site.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        original_environment_recovery(recovery, scope, selection.spec_ref, "SSH")
        return spec, site, snapshot

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        spec, site, snapshot = self._environment(selection, control)
        if operation.recovery_ref != site.token.recovery_ref:
            raise OwnershipConflict("SSH environment changed original recovery")
        return EnvironmentBaseline(
            scope=selection.scope,
            operation=operation,
            allocation=site.token,
            spec_ref=selection.spec_ref,
            checks=self.checks(
                ENVIRONMENT_CHECKS,
                (
                    reference,
                    selection.site_spec_ref,
                    selection.site_started_ref,
                    selection.snapshot_ref,
                    snapshot.native_before.payload_ref,
                ),
                "ORIGINAL_GITLAB_ENVIRONMENT",
            ),
            measured_state_sha256=hashlib.sha256(
                snapshot.state.model_dump_json().encode()
                + snapshot.native_before.payload_ref.sha256.encode()
            ).hexdigest(),
        )
