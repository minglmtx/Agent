"""One fixed DOM read for category navigation; no new request or policy proof."""

import json
from typing import Any
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.task_families.document_health import is_error_document
from .page_capture import PAGE_HEALTH_PROGRAM
from .tasks.navigation_page import CategoryNavigationPage

CATEGORY_PAGE_PROGRAM = (
    "() => { const health = ("
    + PAGE_HEALTH_PROGRAM
    + ")(); return {schema_version:'shopping-category-navigation-page/1',"
    "health,heading_texts:Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'),"
    "h=>h.innerText),document_ready:document.readyState}; }"
)


class ShoppingCategoryPageCollector:
    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if (collector_id, collector_version) != (
            "shopping-category-navigation-page",
            "1",
        ):
            raise ValueError("Unsupported fixed Shopping category collector")
        control.checkpoint()
        fact = CategoryNavigationPage.model_validate_json(
            json.dumps(page.evaluate(CATEGORY_PAGE_PROGRAM), allow_nan=False)
        )
        # DOM cannot grant an independent network-policy fact.
        if fact.navigation_policy_block is not None:
            raise ValueError("Category DOM cannot attest a network-policy block")
        health = fact.health
        changes: dict[str, Any] = {
            "error_page": is_error_document(
                health.url, health.http_status, health.title
            )
        }
        if health.url != page.url:
            changes.update(http_status=None, status_source="document_changed")
        measured = {
            **fact.model_dump(),
            "health": {**health.model_dump(), **changes},
        }
        # The browser engine retains obtained facts before its post-read checkpoint.
        return CategoryNavigationPage.model_validate(measured).model_dump_json()
