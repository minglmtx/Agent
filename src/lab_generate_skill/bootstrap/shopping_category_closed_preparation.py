"""Read only the original category preparation; never authorize native work.

The enclosing closed-source consumer must separately verify original resource
closures and complete source/Reset evidence. This factory only recomputes its
retained preparation through existing readers and original category policies.
"""

from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from .shopping_category_records import (
    bind_category_navigation_records,
    category_preparation_records,
)


class ClosedCategoryPreparationAuthority:
    def __init__(
        self,
        initial: BaselineInputs,
        site: SiteResourceSpec,
        browser: BrowserResourceSpec,
    ) -> None:
        self.initial = BaselineInputs.model_validate(initial)
        self.site = SiteResourceSpec.model_validate(site)
        self.browser = BrowserResourceSpec.model_validate(browser)
        selected = self.browser.configuration.initialization
        old = self.initial
        if (
            self.site.configuration.site_id != "shopping"
            or not isinstance(selected, ShoppingCategoryInitialization)
            or self.site.token.owner != old.prepared.scope.owner
            or self.browser.token.owner != self.site.token.owner
            or self.browser.configuration.spec.scope != old.prepared.scope
            or self.browser.configuration.spec.task != old.public_task
            or self.browser.token.attempt_id != old.prepared.scope.attempt_id
            or selected.prepared_ref != old.prepared_ref
            or old.spec != category_navigation_initial_spec(old.prepared.scope.task)
        ):
            raise OwnershipConflict(
                "Closed category preparation changed original scope/browser/policy"
            )
        selected.check(self.browser.configuration.spec)
        self.selected = selected

    def _guard(self, op: OperationContext, control: OperationControl) -> None:
        control.checkpoint()
        scope = self.initial.prepared.scope
        if (
            op.mode != "cleanup"
            or (op.run_id, op.owner_id) != (scope.owner.run_id, scope.owner.owner_id)
            or op.attempt_id not in (None, scope.attempt_id)
        ):
            raise OwnershipConflict(
                "Closed category preparation requires an original bounded read"
            )

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._guard(op, control)
        old = self.initial
        if (
            binding != old.binding
            or public_task != old.public_task
            or baseline != old.spec.model_dump_json().encode()
        ):
            raise OwnershipConflict("Closed category binding changed original facts")
        # The original binding reader already supplied this complete body. Its
        # category wrapper recomputes native meaning; do not fetch it again.
        require_complete_bytes(binding.private_spec_ref, private_spec)
        private = CategoryNavigationSpec.model_validate_json(private_spec)
        if (
            private.task != old.prepared.scope.task
            or private.native_contract_ref.sha256
            != self.selected.native_contract_sha256
        ):
            raise OwnershipConflict("Closed category native/browser binding changed")
        control.checkpoint()

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._guard(op, control)
        inputs.request.check_site(self.site.configuration)
        old = self.initial
        if (
            inputs.binding != old.binding
            or inputs.public_task != old.public_task
            or inputs.spec != old.spec
            or inputs.environment != old.environment
            or inputs.request.operation != old.preparation.operation
            or checks != old.preparation.checks
        ):
            raise OwnershipConflict(
                "Closed category preparation changed original receipt/checks"
            )
        control.checkpoint()


def closed_category_preparations(
    initial: BaselineInputs,
    site: SiteResourceSpec,
    browser: BrowserResourceSpec,
    store: EvidenceStore,
    controls: OperationControls,
) -> EvidencePreparationRecords:
    authority = ClosedCategoryPreparationAuthority(initial, site, browser)
    return category_preparation_records(
        store,
        controls,
        bind_category_navigation_records(store, controls, authority),
        authority,
    )
