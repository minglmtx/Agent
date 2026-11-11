"""Fake DOM/page only; all real caller/configuration methods remain selected."""

from typing import Any
import hashlib
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from browser_worker_fixtures import configuration
from test_shopping_order_eta_inputs import reference


def browser_configuration(raw: bytes, public: PublicTask) -> BrowserWorkerConfiguration:
    base = configuration()
    session = BrowserSessionSpec.model_validate(
        {
            **base.spec.model_dump(),
            "task": public,
            "scope": base.spec.scope.model_copy(update={"task": public.identity}),
        }
    )
    return BrowserWorkerConfiguration.model_validate(
        {
            **base.model_dump(),
            "spec": session,
            "initialization": ShoppingCategoryInitialization(
                endpoint="http://127.0.0.1:18080/",
                prepared_ref=reference(b"prepared", content_schema="prepared-task/1"),
                site_ref=reference(b"site", content_schema="site-resource-started/1"),
                native_contract_sha256=hashlib.sha256(raw).hexdigest(),
            ),
        }
    )


class Page:
    def __init__(self, task: PublicTask) -> None:
        self.url = "about:blank"
        self.context = self
        self.handlers: list[Any] = []
        self.visits: list[str] = []
        self.failure = False
        self.health: dict[str, Any] = {
            "schema_version": "shopping-page-health/1",
            "url": task.start_url,
            "http_status": 200,
            "status_source": "navigation_timing",
            "title": "Storefront",
            "login_page": False,
            "error_page": False,
        }
        self.ready = "complete"

    def route(self, pattern: str, handler: Any) -> None:
        assert pattern == "**/*"
        self.handlers.append(handler)

    def goto(self, url: str, **kwargs: Any) -> None:
        assert kwargs["timeout"] > 0
        self.visits.append(url)
        self.url = url

    def wait_for_function(self, program: str, **kwargs: Any) -> None:
        assert "readyState" in program
        if self.failure:
            raise TimeoutError("Original document readiness unconfirmed")

    def evaluate(self, program: str) -> dict[str, Any]:
        return {
            "schema_version": "shopping-category-navigation-page/1",
            "health": self.health,
            "heading_texts": ["Original storefront"],
            "document_ready": self.ready,
        }
