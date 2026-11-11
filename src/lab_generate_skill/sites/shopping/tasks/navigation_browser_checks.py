"""Join already verified preparation/request bodies to this original browser."""

from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_admission import task_input


class CategoryNavigationBrowserChecks:
    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if not isinstance(initialization, ShoppingCategoryInitialization):
            raise ValueError(
                "Explicit original category browser initialization required"
            )
        request.check_site(site_spec.configuration)
        private = task_input(request).spec
        if (
            request.action != "prepare"
            or request.task != private.task
            or initialization.prepared_ref != publication.prepared_ref
            or initialization.endpoint != site.instance.endpoint
            or initialization.native_contract_sha256
            != private.native_contract_ref.sha256
        ):
            raise OwnershipConflict(
                "Category browser changed original private preparation/origin"
            )
        # PreparationRecords already validates CategoryNavigationInputs against
        # the original public task. The generic caller compares that exact
        # PreparedTask to config.spec.task; no duplicate storage read is needed.
        control.checkpoint()
