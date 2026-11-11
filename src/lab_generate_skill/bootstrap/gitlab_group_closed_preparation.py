"""Original Group preparation verification after complete resource closure."""

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
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.group_preparation_checks import (
    GroupPreparationChecks,
)
from .gitlab_group_source import GroupSourceSelection
from .gitlab_group_capture import load_group_capture


class ClosedGroupPreparationAuthority:
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
        if (
            site.configuration.site_id != "gitlab"
            or site.configuration.private_evidence is None
            or site.configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or initial.prepared.scope != browser.configuration.spec.scope
            or initial.prepared.scope.owner != site.token.owner
        ):
            raise OwnershipConflict(
                "Closed Group preparation changed original scope/profile"
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
                "Closed Group binding changed original immutable facts"
            )
        private = GroupSpec.model_validate_json(private_spec)
        raw = self.store.read(private.native_contract_ref, control)
        selected = GroupSourceSelection(raw, public_task)
        if selected.load(
            private.native_contract_ref, public_task
        ) != private or old.spec != group_initial_spec(binding.identity):
            raise OwnershipConflict(
                "Closed Group binding changed original native meaning"
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
                "Closed Group preparation changed original receipt/checks"
            )
        control.checkpoint()


def closed_group_preparations(
    initial: BaselineInputs,
    site: SiteResourceSpec,
    browser: BrowserResourceSpec,
    store: EvidenceStore,
    controls: OperationControls,
) -> EvidencePreparationRecords:
    authority = ClosedGroupPreparationAuthority(initial, site, browser, store)
    return EvidencePreparationRecords(
        store,
        controls,
        EvidenceTaskBindings(store, controls, authority),
        GroupPreparationChecks(store, load_group_capture),
        authority,
    )
