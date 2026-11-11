"""Navigate the exact original start once; no ETA login/date or target actions."""

import os
import threading
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from .navigation_page_capture import ShoppingCategoryPageCollector
from .tasks.navigation_page import CategoryNavigationPage


class ShoppingCategoryBrowserInitializer:
    def __init__(self, config: ShoppingCategoryInitialization) -> None:
        self.config = ShoppingCategoryInitialization.model_validate(config)
        self.owner = os.getpid(), threading.get_ident()
        self.attempted = False

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Original browser context owns category initialization"
            )
        if self.attempted:
            raise InvalidTransition("Category initialization already attempted")
        control.checkpoint()
        task = PublicTask.model_validate(task)
        self.config.check_task(task)
        if page.url != "about:blank":
            raise OwnershipConflict("Category requires the original first document")
        self.attempted = True
        origin = urlsplit(self.config.endpoint)

        def local_only(route: Any) -> None:
            url = urlsplit(route.request.url)
            if url.scheme in ("data", "blob", "about") or (url.scheme, url.netloc) == (
                origin.scheme,
                origin.netloc,
            ):
                route.continue_()
            else:
                route.abort()

        page.context.route("**/*", local_only)
        page.goto(
            task.start_url,
            wait_until="load",
            timeout=min(60000, control.checkpoint() * 1000),
        )
        page.wait_for_function(
            "() => document.readyState === 'complete'",
            timeout=min(15000, control.checkpoint() * 1000),
        )
        fact = CategoryNavigationPage.model_validate_json(
            ShoppingCategoryPageCollector().collect(
                page, "shopping-category-navigation-page", "1", control
            )
        )
        if (
            page.url != task.start_url
            or fact.health.url != task.start_url
            or fact.document_ready != "complete"
            or fact.health.http_status is None
            or not 200 <= fact.health.http_status < 300
            or fact.health.login_page
            or fact.health.error_page
        ):
            raise OwnershipConflict(
                "Original category start document is not confirmed healthy"
            )
        control.checkpoint()
