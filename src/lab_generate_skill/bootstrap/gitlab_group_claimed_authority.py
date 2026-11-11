"""Original Group input/origin checks on the existing claimed site owner."""

import hashlib
from urllib.parse import urlsplit

from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.gitlab_group_origin import GitlabGroupWorkerInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec


class GroupClaimedSiteAuthority(ClaimedSiteResourceAuthority):
    def verify_site_inputs(self) -> None:
        cfg, owner = self.spec.configuration, self.owner
        inputs = cfg.gitlab_group_inputs
        if (
            cfg.schema_version != "site-worker-configuration/8"
            or cfg.site_id != "gitlab"
            or not isinstance(inputs, GitlabGroupWorkerInputs)
            or cfg.private_evidence is None
            or cfg.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or self.spec.token.owner != owner.run.owner
            or inputs.scope.owner != owner.run.owner
            or inputs.scope.task != owner.task.identity
            or self.spec.slurm.execution != owner.authority.execution
            or self.spec.slurm.parent != owner.authority.controller
        ):
            raise OwnershipConflict(
                "Original Group version8 owner/profile/controller required"
            )

    def verify_source(
        self, operation: OperationContext, control: OperationControl
    ) -> None:
        self.verify_site_inputs()
        inputs = self.spec.configuration.gitlab_group_inputs
        assert inputs is not None
        # This rereads original live claim/run/source permission on each call.
        source = self.owner.task_source(operation, control)
        private = self.owner.reads.parse(
            self.owner.task.private_spec_ref,
            "gitlab-group-creation/1",
            GroupSpec,
            control,
        )
        public = self.owner.reads.parse(
            source.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        reset = self.owner.reads.parse(
            self.owner.task_plan.reset_plan_ref, "reset-plan/1", ResetPlan, control
        )
        start = urlsplit(public.task.start_url)
        if (
            inputs.scope != reset.scope
            or inputs.scope.attempt_id != source.intent.binding.attempt_id
            or inputs.scope.task != source.task.identity
            or private.task != source.task.identity
            or public.task.identity != private.task
            or inputs.native_contract_sha256 != private.native_contract_ref.sha256
            or inputs.private_input_sha256
            != hashlib.sha256(private.model_dump_json().encode()).hexdigest()
            or start.scheme != "http"
            or start.hostname != "127.0.0.1"
            or start.username is not None
            or start.password is not None
            or start.port != inputs.origin.web_port
        ):
            raise OwnershipConflict(
                "Group changed original full scope/native input/public origin"
            )
        control.checkpoint()

    def verify_origin(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if spec != self.spec:
            raise OwnershipConflict("Group origin changed original site declaration")
        self.spec.check_operation(operation, "execute")
        self.verify_source(operation, control)
