"""Selected fixed consumer: one DOM read, full headings and explicit missing state."""

from types import SimpleNamespace
from typing import Any, cast
import pytest
from lab_generate_skill.bootstrap.browser_capture import browser_collector
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    CATEGORY_PAGE_PROGRAM,
    ShoppingCategoryPageCollector,
)
from lab_generate_skill.sites.shopping.page_capture import ShoppingPageHealthCollector
from lab_generate_skill.sites.shopping.tasks.navigation_page import (
    CategoryNavigationPage,
)

URL = "http://127.0.0.1:18080/electronics.html"


def selection(family: str, *, split: str = "train", version: int = 1) -> Any:
    return cast(
        BrowserWorkerConfiguration,
        SimpleNamespace(
            spec=SimpleNamespace(
                task=SimpleNamespace(
                    identity=SimpleNamespace(
                        site="shopping",
                        family=family,
                        contract_version=version,
                        split=split,
                    )
                )
            )
        ),
    )


@pytest.mark.parametrize(
    "fault",
    [
        "normal",
        "empty",
        "many",
        "missing_status",
        "changed",
        "loading",
        "cancel_before",
        "cancel_after",
        "native",
        "collector",
        "version",
        "missing_headings",
        "wrong_heading_type",
        "missing_ready",
        "wrong_ready",
        "forged_block",
    ],
)
def test_fixed_single_read_and_capture_boundaries(fault: str) -> None:
    calls: list[str] = []
    value: dict[str, Any] = {
        "schema_version": "shopping-category-navigation-page/1",
        "health": {
            "schema_version": "shopping-page-health/1",
            "url": URL,
            "title": "Electronics",
            "http_status": 200,
            "status_source": "navigation_timing",
            "login_page": False,
            "error_page": False,
        },
        "heading_texts": ["Electronics", "Cameras"],
        "document_ready": "complete",
    }
    if fault == "empty":
        value["heading_texts"] = []
    if fault == "many":
        value["heading_texts"] = [str(i) for i in range(1200)]
    if fault == "missing_status":
        value["health"].update(http_status=None, status_source="unavailable")
    if fault == "loading":
        value["document_ready"] = "loading"
    if fault == "missing_headings":
        del value["heading_texts"]
    if fault == "wrong_heading_type":
        value["heading_texts"] = [True]
    if fault == "missing_ready":
        del value["document_ready"]
    if fault == "wrong_ready":
        value["document_ready"] = 1
    if fault == "forged_block":
        value["navigation_policy_block"] = {
            "source": "local_network_policy",
            "reason": "outside_declared_local_services",
            "document_url": "chrome-error://chromewebdata/",
            "blocked_origin": "https://outside.example",
        }
    stopped = False

    def checkpoint() -> None:
        if stopped:
            raise OSError("cancelled")

    def evaluate(program: str) -> dict[str, Any]:
        nonlocal stopped
        assert program == CATEGORY_PAGE_PROGRAM
        calls.append(program)
        if fault == "native":
            raise OSError("native failure")
        if fault == "cancel_after":
            stopped = True
        return value

    page = SimpleNamespace(
        evaluate=evaluate, url=URL + "changed" if fault == "changed" else URL
    )
    local_control = cast(Any, SimpleNamespace(checkpoint=checkpoint))
    if fault == "cancel_before":
        stopped = True
    collector = ShoppingCategoryPageCollector()
    if fault in (
        "cancel_before",
        "native",
        "collector",
        "version",
        "missing_headings",
        "wrong_heading_type",
        "missing_ready",
        "wrong_ready",
        "forged_block",
    ):
        with pytest.raises((ValueError, OSError)):
            collector.collect(
                page,
                (
                    "other"
                    if fault == "collector"
                    else "shopping-category-navigation-page"
                ),
                "2" if fault == "version" else "1",
                local_control,
            )
    else:
        result = CategoryNavigationPage.model_validate_json(
            collector.collect(
                page, "shopping-category-navigation-page", "1", local_control
            )
        )
        assert result.heading_texts == tuple(value["heading_texts"])
        assert result.document_ready == value["document_ready"]
        assert result.health.http_status == (
            None if fault in ("changed", "missing_status") else 200
        )
        assert result.navigation_policy_block is None
        if fault == "changed":
            assert result.health.status_source == "document_changed"
        if fault == "cancel_after":
            with pytest.raises(OSError):
                local_control.checkpoint()
    assert len(calls) == (
        0 if fault in ("cancel_before", "collector", "version") else 1
    )


def test_actual_fixed_selector_and_unaffected_eta_branch() -> None:
    assert isinstance(
        browser_collector(selection("page_navigation")), ShoppingCategoryPageCollector
    )
    assert isinstance(
        browser_collector(selection("recorded_order_eta")), ShoppingPageHealthCollector
    )
    assert browser_collector(selection("page_navigation", version=2)) is None
    assert browser_collector(selection("page_navigation", split="test")) is None
    assert browser_collector(selection("other")) is None
