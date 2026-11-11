"""Authenticate and navigate the declared start before the unique observation."""

from typing import Any, Callable
from urllib.parse import urlsplit
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .authenticated_browser import authenticate_admin


class AdminNavigationBrowserInitializer:
    def __init__(
        self,
        config: AdminNavigationInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        self.config = AdminNavigationInitialization.model_validate(config)
        self.login = login
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.attempted:
            raise RuntimeError("Admin navigation initialization was already attempted")
        control.checkpoint()
        self.config.check_task(task)
        self.attempted = True
        authenticate_admin(page, self.config.endpoint, self.login, control)

        def timeout() -> float:
            return min(60000, control.checkpoint() * 1000)

        page.goto(task.start_url, wait_until="domcontentloaded", timeout=timeout())
        page.wait_for_selector("body#html-body", timeout=timeout())
        page.wait_for_selector("h1", timeout=timeout())
        if page.locator(
            'form#login-form input[type="password"],body.adminhtml-auth-login input[type="password"]'
        ).count():
            raise RuntimeError("Admin navigation login did not complete")
        actual, wanted = urlsplit(page.url), urlsplit(self.config.endpoint)
        if (actual.scheme, actual.netloc) != (wanted.scheme, wanted.netloc):
            raise RuntimeError("Admin navigation left original instance")
        # Actual initial route/DOM qualification is a separate recorded check;
        # this setup does not infer trajectory equivalence or inspect a target.
        control.checkpoint()
