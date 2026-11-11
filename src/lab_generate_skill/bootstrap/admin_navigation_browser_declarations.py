"""Admin navigation initialization on the original late immutable browser declarations."""

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from .task_browser_declarations import OriginalTaskBrowserDeclarations


class OriginalAdminNavigationBrowserDeclarations(OriginalTaskBrowserDeclarations):
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        model: ActorExecutionScope,
        reset: ResetPlan,
        template: BrowserWorkerConfiguration,
        actor: TaskActorInitialization,
    ) -> None:
        def initialization(
            prep: RecordedSiteTaskPreparation,
            prepared: EvidenceRef,
            site: EvidenceRef,
            control: OperationControl,
        ) -> AdminNavigationInitialization:
            private = owner.reads.parse(
                owner.task.private_spec_ref,
                "shopping-admin-page-navigation/1",
                AdminNavigationSpec,
                control,
            )
            return AdminNavigationInitialization(
                endpoint=prep.site.site.instance.endpoint,
                prepared_ref=prepared,
                site_ref=site,
                native_contract_sha256=private.native_contract_ref.sha256,
                start_path=private.start_path,
            )

        super().__init__(
            owner,
            model,
            reset,
            template,
            actor,
            initialization=initialization,
            producer="admin-navigation-task-browser-declarations",
        )
