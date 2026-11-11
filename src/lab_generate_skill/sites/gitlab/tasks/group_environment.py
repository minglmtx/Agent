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
from .group_reads import GroupStateReads
from ..environment_identity import original_environment, original_environment_recovery
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from .group_spec import GroupSpec
from .group_request import task_input
from .group_recovery import GroupRecoverySnapshot
from .group_rules import validate_group_initial
from .group_policy import (
    group_initial_spec,
    ENVIRONMENT_CHECKS,
    ENVIRONMENT_RESET_CHECKS,
)


class GroupEnvironmentChecks(GroupStateReads):
    def _environment(
        self, selection: EnvironmentSelection, control: OperationControl
    ) -> tuple[InitialStateSpec, SiteResourceSpec, GroupRecoverySnapshot]:
        selection = EnvironmentSelection.model_validate(selection)
        spec = self.read(
            selection.spec_ref, "initial-state-spec/1", InitialStateSpec, control
        )
        if spec != group_initial_spec(selection.scope.task):
            raise ValueError("Unsupported or incomplete Group initial-state coverage")
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
            "gitlab-group-recovery/1",
            GroupRecoverySnapshot,
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
            raise OwnershipConflict("Group environment changed original scope")
        binding = self.read(request.binding_ref, "task-binding/1", TaskBinding, control)
        bound = self.read(
            binding.private_spec_ref, "gitlab-group-creation/1", GroupSpec, control
        )
        if (binding.identity, binding.baseline_ref, bound) != (
            scope.task,
            selection.spec_ref,
            private,
        ):
            raise OwnershipConflict(
                "Group environment changed original private binding/spec"
            )
        original_environment(
            site,
            started,
            snapshot.state,
            snapshot.native_before.context,
            GITLAB_GROUP_PRIVATE_JSON,
            "Group",
        )
        before = self.native(snapshot.native_before, request, control)
        validate_group_initial(private, before.state)
        recovery = self.read(
            site.token.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        original_environment_recovery(recovery, scope, selection.spec_ref, "Group")
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
            raise OwnershipConflict("Group environment changed original recovery")
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
