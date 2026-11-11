"""Read original Admin navigation preparation after complete resource closure.

No live site/native supplier is reused, and no binding or task grant is issued.
Existing record readers and navigation predicates recompute the original facts.
"""

import hashlib
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from .admin_navigation import load_admin_navigation_inputs


class ClosedAdminNavigationPreparationAuthority:
    def __init__(
        self,
        initial: BaselineInputs,
        site: SiteResourceSpec,
        browser: BrowserResourceSpec,
        store: EvidenceStore,
    ) -> None:
        self.initial, self.site, self.browser, self.store = (
            initial,
            site,
            browser,
            store,
        )
        inputs = site.configuration.admin_navigation_inputs
        if (
            inputs is None
            or initial.prepared.scope != inputs.scope
            or initial.prepared.scope != browser.configuration.spec.scope
        ):
            raise OwnershipConflict(
                "Closed Admin preparation changed original source scope"
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
        control.checkpoint()
        old = self.initial
        if (
            op.mode != "cleanup"
            or binding != old.binding
            or public_task != old.public_task
            or baseline != old.spec.model_dump_json().encode()
            or private_spec != self.store.read(binding.private_spec_ref, control)
            or old.prepared.scope != self.browser.configuration.spec.scope
        ):
            raise OwnershipConflict(
                "Closed Admin source binding changed immutable original facts"
            )
        private = AdminNavigationSpec.model_validate_json(private_spec)
        raw = self.store.read(private.native_contract_ref, control)
        original = load_admin_navigation_inputs(
            raw, private.native_contract_ref, public_task
        )
        inputs = self.site.configuration.admin_navigation_inputs
        if (
            original.private_spec != private
            or old.spec != navigation_initial_state_spec(binding.identity)
            or inputs is None
            or inputs.native_contract_sha256 != private.native_contract_ref.sha256
            or inputs.private_input_sha256
            != hashlib.sha256(
                NavigationExecutionInput(spec=private).model_dump_json().encode()
            ).hexdigest()
        ):
            raise OwnershipConflict(
                "Closed Admin source changed original native meaning"
            )
        control.checkpoint()

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        old = self.initial
        inputs.request.check_site(self.site.configuration)
        if (
            op.mode != "cleanup"
            or inputs.binding != old.binding
            or inputs.public_task != old.public_task
            or inputs.spec != old.spec
            or inputs.environment != old.environment
            or inputs.request.operation != old.preparation.operation
            or checks != old.preparation.checks
        ):
            raise OwnershipConflict(
                "Closed Admin preparation changed original receipt/checks"
            )
        control.checkpoint()


def closed_admin_navigation_preparations(
    initial: BaselineInputs,
    site: SiteResourceSpec,
    browser: BrowserResourceSpec,
    store: EvidenceStore,
    controls: OperationControls,
) -> EvidencePreparationRecords:
    authority = ClosedAdminNavigationPreparationAuthority(initial, site, browser, store)
    return EvidencePreparationRecords(
        store,
        controls,
        EvidenceTaskBindings(store, controls, authority),
        NavigationPreparationChecks(store),
        authority,
    )
