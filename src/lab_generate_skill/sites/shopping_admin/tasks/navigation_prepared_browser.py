"""Exact navigation initialization join; outer original resource authority remains."""

from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_recovery_contract import NavigationExecutionInput


class NavigationPreparedBrowserChecks:
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
        if not isinstance(initialization, AdminNavigationInitialization):
            raise ValueError("Explicit original navigation initialization required")
        request.check_site(site_spec.configuration)
        data = NavigationExecutionInput.model_validate_json(request.private_input)
        if (
            request.action != "prepare"
            or data.model_dump_json() != request.private_input
            or data.spec.task != request.task
            or (
                initialization.endpoint,
                initialization.prepared_ref,
                initialization.native_contract_sha256,
                initialization.start_path,
            )
            != (
                site.instance.endpoint,
                publication.prepared_ref,
                data.spec.native_contract_ref.sha256,
                data.spec.start_path,
            )
        ):
            raise OwnershipConflict(
                "Navigation initialization changed original preparation/source/start"
            )
        control.checkpoint()
