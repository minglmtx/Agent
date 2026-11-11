"""Exact category inputs/origin on current claimed site rights; no live defaults."""

import hashlib
from lab_generate_skill.adapters.sites.claimed_authority import (
    ClaimedSiteResourceAuthority,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.shopping_navigation_origin import (
    ShoppingCategoryWorkerInputs,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.policies.evidence_bytes import require_complete_read_bound
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA


class CategoryNavigationClaimedSiteAuthority(ClaimedSiteResourceAuthority):
    def verify_site_inputs(self) -> None:
        cfg, owner = self.spec.configuration, self.owner
        inputs = cfg.shopping_category_inputs
        if (
            cfg.site_id != "shopping"
            or cfg.schema_version != "site-worker-configuration/9"
            or not isinstance(inputs, ShoppingCategoryWorkerInputs)
            or cfg.files.image.sha256 != SHOPPING_IMAGE_SHA
            or self.spec.token.owner != owner.run.owner
            or inputs.scope.owner != owner.run.owner
            or inputs.scope.task != owner.task.identity
            or self.spec.slurm.execution != owner.authority.execution
            or self.spec.slurm.parent != owner.authority.controller
        ):
            raise OwnershipConflict(
                "Original category version9 owner/image/controller required"
            )
        category_navigation_initial_spec(owner.task.identity)

    def verify_source(
        self, operation: OperationContext, control: OperationControl
    ) -> None:
        self.verify_site_inputs()
        inputs = self.spec.configuration.shopping_category_inputs
        assert inputs is not None
        # This call retains current claim/run/source and storage admission.
        source = self.owner.task_source(operation, control)
        for reference in (
            self.owner.task.private_spec_ref,
            source.public_context_ref,
            self.owner.task_plan.reset_plan_ref,
        ):
            require_complete_read_bound(reference, 2 * 1024**2)
        private = self.owner.reads.parse(
            self.owner.task.private_spec_ref,
            "shopping-category-navigation/1",
            CategoryNavigationSpec,
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
        canonical = (
            CategoryNavigationExecutionInput(spec=private).model_dump_json().encode()
        )
        if (
            inputs.scope != reset.scope
            or inputs.scope.attempt_id != source.intent.binding.attempt_id
            or inputs.scope.task != source.task.identity
            or private.task != source.task.identity
            or public.task.identity != private.task
            or inputs.native_contract_sha256 != private.native_contract_ref.sha256
            or inputs.private_input_sha256 != hashlib.sha256(canonical).hexdigest()
            or public.task.goal != private.original.goal
            or public.task.start_url
            != inputs.origin.endpoint.rstrip("/") + private.original.start_path
        ):
            raise OwnershipConflict(
                "Category changed original full scope/native/public input/origin"
            )
        control.checkpoint()

    def verify_origin(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if spec != self.spec:
            raise OwnershipConflict("Category origin changed original site declaration")
        self.spec.check_operation(operation, "execute")
        self.verify_source(operation, control)
