"""Fixed native document facts, explicit unknown and exact legacy error rule."""

from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.sites.shopping.page_capture import (
    ShoppingPageHealthCollector,
    ShoppingPageHealth,
    PAGE_HEALTH_PROGRAM,
)
from lab_generate_skill.task_families.document_health import is_error_document
from lab_generate_skill.browser_http_status import (
    is_error_document as historical_error_rule,
)
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "missing",
        "changed",
        "bool",
        "string",
        "zero",
        "collector",
        "version",
        "native",
    ],
)
def test_original_document_read_and_fail_closed_status(fault: str) -> None:
    calls: list[str] = []
    url = "http://127.0.0.1:12001/customer/account/"

    def evaluate(script: str) -> dict[str, Any]:
        calls.append(script)
        assert script == PAGE_HEALTH_PROGRAM
        if fault == "native":
            raise OSError("original page unavailable")
        return dict(
            schema_version="shopping-page-health/1",
            url=url,
            title="Account Dashboard",
            http_status=(
                None
                if fault == "missing"
                else (
                    True
                    if fault == "bool"
                    else "200" if fault == "string" else 0 if fault == "zero" else 200
                )
            ),
            status_source="unavailable" if fault == "missing" else "navigation_timing",
            login_page=False,
            error_page=False,
        )

    page = SimpleNamespace(
        evaluate=evaluate, url=url + "changed" if fault == "changed" else url
    )
    collector = ShoppingPageHealthCollector()
    if fault in ("none", "missing", "changed"):
        result = ShoppingPageHealth.model_validate_json(
            collector.collect(page, "shopping-page-health", "1", guard())
        )
        assert result.http_status == (200 if fault == "none" else None)
        assert (
            result.status_source
            == {
                "none": "navigation_timing",
                "missing": "unavailable",
                "changed": "document_changed",
            }[fault]
        )
        assert result.url == url and not result.error_page
    else:
        with pytest.raises((ValueError, OSError)):
            collector.collect(
                page,
                "other" if fault == "collector" else "shopping-page-health",
                "2" if fault == "version" else "1",
                guard(),
            )
    assert len(calls) == (0 if fault in ("collector", "version") else 1)


@pytest.mark.parametrize(
    "url,status,title,expected",
    [
        ("http://local/", 200, "Account", False),
        ("http://local/", 404, "Account", True),
        ("http://local/", 500, "Account", True),
        ("http://local/", 200, "Whoops, our bad...", True),
        ("http://local/", 200, "Page not found | One Stop Market", True),
        ("http://local/", 200, "Documentation: page not found", False),
        ("http://local/", None, "Account", False),
        ("chrome-error://chromewebdata/", None, "", True),
    ],
)
def test_original_error_predicate_reexport_and_exact_semantics(
    url: str, status: int | None, title: str, expected: bool
) -> None:
    assert historical_error_rule is is_error_document
    assert is_error_document(url, status, title) == expected
