"""Admin navigation input/origin on the original claimed Site lifecycle."""

import hashlib
from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)


class AdminNavigationClaimedSiteAuthority(ClaimedSiteResourceAuthority):
    def verify_site_inputs(self) -> None:
        cfg, owner = self.spec.configuration, self.owner
        inputs = cfg.admin_navigation_inputs
        if (
            cfg.site_id != "shopping_admin"
            or cfg.schema_version != "site-worker-configuration/7"
            or not isinstance(inputs, AdminNavigationWorkerInputs)
            or (
                self.spec.token.owner != owner.run.owner
                or inputs.scope.owner != owner.run.owner
                or inputs.scope.task != owner.task.identity
                or self.spec.slurm.execution != owner.authority.execution
                or self.spec.slurm.parent != owner.authority.controller
            )
        ):
            raise OwnershipConflict(
                "Original current Admin navigation task/site/controller required"
            )

    def verify_source(
        self, operation: OperationContext, control: OperationControl
    ) -> None:
        self.verify_site_inputs()
        inputs = self.spec.configuration.admin_navigation_inputs
        assert inputs is not None
        source = self.owner.task_source(operation, control)
        private = self.owner.reads.parse(
            self.owner.task.private_spec_ref,
            "shopping-admin-page-navigation/1",
            AdminNavigationSpec,
            control,
        )
        public = self.owner.reads.parse(
            source.public_context_ref,
            "public-construction-context/1",
            PublicConstructionContext,
            control,
            visibility="public",
        )
        canonical = NavigationExecutionInput(spec=private).model_dump_json().encode()
        if (
            inputs.scope.attempt_id != source.intent.binding.attempt_id
            or inputs.scope.task != source.task.identity
            or private.task != source.task.identity
            or public.task.identity != private.task
            or inputs.native_contract_sha256 != private.native_contract_ref.sha256
            or inputs.private_input_sha256 != hashlib.sha256(canonical).hexdigest()
            or public.task.start_url != inputs.origin.endpoint + private.start_path
        ):
            raise OwnershipConflict(
                "Admin site changed original qualified source/native input/origin"
            )
