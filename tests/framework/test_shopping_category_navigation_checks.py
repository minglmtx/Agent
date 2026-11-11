"""Original category oracle comparison and missing-vs-negative fact boundaries."""

import json
from collections.abc import Callable
from typing import Any, cast
import pytest
from pydantic import ValidationError
from test_shopping_category_navigation_input import (
    originals as originals,
    reference,
)
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill import site_navigation_rules
from lab_generate_skill.sites.shopping.evidence_schema import ShoppingPageHealth
from lab_generate_skill.sites.shopping.tasks.navigation_checks import (
    CHECKS,
    IncompleteCategoryNavigation,
    category_navigation_checks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_page import (
    CategoryNavigationBlock,
    CategoryNavigationPage,
)

ORIGIN = "http://127.0.0.1:18080"
evaluate_navigation = cast(
    Callable[..., dict[str, Any]], site_navigation_rules.evaluate_navigation
)


def page(**changes: Any) -> CategoryNavigationPage:
    health = ShoppingPageHealth(
        url=ORIGIN + "/electronics.html",
        http_status=200,
        status_source="navigation_timing",
        title="Electronics",
        login_page=False,
        error_page=False,
    )
    value = CategoryNavigationPage(
        health=health, heading_texts=("Electronics",), document_ready="complete"
    )
    for key, change in changes.items():
        if key in ("url", "http_status", "login_page", "error_page", "status_source"):
            health = value.health.model_copy(update={key: change})
            value = value.model_copy(update={"health": health})
        else:
            value = value.model_copy(update={key: change})
    return CategoryNavigationPage.model_validate_json(value.model_dump_json())


def test_original_v3_predicate_preserved_for_all18_native_contracts(
    originals: Any,
) -> None:
    examples = [
        page(),
        page(heading_texts=("ELECTRONICS",)),
        page(url=ORIGIN + "/%65lectronics.html"),
        page(url=ORIGIN + "/books.html", heading_texts=("Books",)),
        page(url="http://127.0.0.1:18081/electronics.html"),
        page(http_status=302),
        page(http_status=404, error_page=True),
        page(login_page=True),
        page(heading_texts=()),
    ]
    for raw, native, public in originals:
        spec = load_category_navigation_inputs(raw, reference(raw), public).private_spec
        for value in examples:
            old_page = value.health.model_dump(
                mode="json", exclude={"schema_version", "status_source"}
            )
            old_page["heading_texts"] = list(value.heading_texts)
            original = evaluate_navigation(native, old_page, site_origin=ORIGIN)
            actual = category_navigation_checks(spec, value, ORIGIN)
            assert tuple(actual) == CHECKS
            assert actual == original["checks"]
            assert int(all(actual.values())) == original["reward"]
    first = load_category_navigation_inputs(
        originals[0][0], reference(originals[0][0]), originals[0][2]
    ).private_spec
    assert all(category_navigation_checks(first, page(), ORIGIN).values())
    assert not all(
        category_navigation_checks(first, page(heading_texts=()), ORIGIN).values()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"document_ready": "loading"},
        {"document_ready": "interactive"},
        {"http_status": None, "status_source": "unavailable"},
        {"http_status": None, "status_source": "document_changed"},
        {"http_status": 199},
        {"http_status": 500},
        {"http_status": 503},
    ],
)
def test_incomplete_or_transport_failure_is_unknown_not_empty_or_negative(
    originals: Any, changes: dict[str, Any]
) -> None:
    raw, _, public = originals[0]
    spec = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    with pytest.raises(IncompleteCategoryNavigation):
        category_navigation_checks(spec, page(**changes), ORIGIN)


def test_exact_outside_service_block_remains_original_valid_negative(
    originals: Any,
) -> None:
    raw, native, public = originals[0]
    spec = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    block = CategoryNavigationBlock(
        source="local_network_policy",
        reason="outside_declared_local_services",
        document_url="chrome-error://chromewebdata/",
        blocked_origin="https://outside.example",
    )
    value = page(
        url=block.document_url,
        http_status=None,
        status_source="unavailable",
        error_page=True,
        navigation_policy_block=block,
    )
    expected = evaluate_navigation(
        native,
        {
            "url": value.health.url,
            "http_status": None,
            "heading_texts": [],
            "title": "Error",
            "login_page": False,
            "error_page": True,
            "navigation_policy_block": block.model_dump(mode="json"),
        },
        site_origin=ORIGIN,
    )
    checks = category_navigation_checks(spec, value, ORIGIN)
    assert checks == expected["checks"]
    assert expected["status"] == "failure" and expected["reward"] == 0
    for bad in (None, block.model_copy(update={"blocked_origin": ORIGIN})):
        with pytest.raises(IncompleteCategoryNavigation):
            category_navigation_checks(
                spec, value.model_copy(update={"navigation_policy_block": bad}), ORIGIN
            )


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://",
        "https://user@host",
        ORIGIN + "/path",
        ORIGIN + "?query=1",
        "file:///tmp",
    ],
)
def test_invalid_declared_origin_refused(originals: Any, origin: str) -> None:
    raw, _, public = originals[0]
    spec = load_category_navigation_inputs(raw, reference(raw), public).private_spec
    with pytest.raises(ValueError):
        category_navigation_checks(spec, page(), origin)


@pytest.mark.parametrize(
    "field,value",
    [
        ("heading_texts", None),
        ("heading_texts", [1]),
        ("document_ready", ""),
        ("health", {}),
    ],
)
def test_missing_or_wrong_page_types_refused(field: str, value: Any) -> None:
    data = page().model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        CategoryNavigationPage.model_validate_json(json.dumps(data))
