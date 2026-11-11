"""Selected Admin login and public task navigation, before the sole observation.

No control scripts, private target values, inferred product routes or actions are
read here. Reuse the established login controls and DOM readiness. The caller
must verify original prepared/site evidence and exclusive browser permission.
"""

from typing import Any, Callable
import re
from urllib.parse import urlsplit
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.browser_initialization import AdminProductInitialization
from lab_generate_skill.ports.lifecycle import OperationControl
from .authenticated_browser import authenticate_admin


class AdminProductBrowserInitializer:
    def __init__(
        self,
        config: AdminProductInitialization,
        login: Callable[[OperationControl], tuple[str, str]],
    ) -> None:
        self.config = AdminProductInitialization.model_validate(config)
        self.endpoint, self.login = self.config.endpoint, login
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.attempted:
            raise RuntimeError("Admin browser initialization was already attempted")
        control.checkpoint()
        self.config.check_task(task)
        self.attempted = True
        origin = urlsplit(self.endpoint)
        if urlsplit(task.start_url).netloc != origin.netloc:
            raise ValueError("Admin task start differs from original endpoint")
        authenticate_admin(page, self.endpoint, self.login, control)

        def timeout() -> float:
            return min(60000, control.checkpoint() * 1000)

        page.goto(task.start_url, wait_until="domcontentloaded", timeout=timeout())
        page.wait_for_selector("body#html-body", timeout=timeout())
        page.wait_for_selector("h1", timeout=timeout())
        page.wait_for_selector('input[name="product[name]"]', timeout=timeout())
        if page.locator(
            'form#login-form input[type="password"],body.adminhtml-auth-login input[type="password"]'
        ).count():
            raise RuntimeError("Admin login did not complete")
        actual = urlsplit(page.url)
        expected_id = re.search(r"/id/([0-9]+)/", urlsplit(task.start_url).path)
        actual_id = re.search(r"/catalog/product/edit/id/([0-9]+)/", actual.path)
        if (
            (actual.scheme, actual.netloc) != (origin.scheme, origin.netloc)
            or expected_id is None
            or actual_id is None
            or expected_id[1] != actual_id[1]
        ):
            raise RuntimeError("Admin task did not reach its original product page")
        control.checkpoint()
