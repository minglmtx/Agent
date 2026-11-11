"""Shopping category navigation initialization on the original late immutable browser declarations."""

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from .task_browser_declarations import OriginalTaskBrowserDeclarations


class OriginalShoppingCategoryBrowserDeclarations(OriginalTaskBrowserDeclarations):
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
        ) -> ShoppingCategoryInitialization:
            private = owner.reads.parse(
                owner.task.private_spec_ref,
                "shopping-category-navigation/1",
                CategoryNavigationSpec,
                control,
            )
            return ShoppingCategoryInitialization(
                endpoint=prep.site.site.instance.endpoint,
                prepared_ref=prepared,
                site_ref=site,
                native_contract_sha256=private.native_contract_ref.sha256,
            )

        super().__init__(
            owner,
            model,
            reset,
            template,
            actor,
            initialization=initialization,
            producer="shopping-category-navigation-task-browser-declarations",
        )
