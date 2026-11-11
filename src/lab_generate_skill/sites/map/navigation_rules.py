"""Selected original page/route rules and guard priority, without native I/O."""

import json
import re
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit, unquote
from .tasks.navigation_spec import NavigationSpec, NavigationCompletion
from .navigation_evidence_schema import NavigationOutcome
from .navigation_route_rules import route_checks


def original_completion(value: NavigationCompletion) -> dict[str, Any]:
    value = NavigationCompletion.model_validate(value)
    result: dict[str, Any] = {
        "path_regex": value.path_regex,
        "heading_regex": value.heading_regex,
    }
    route = value.map_route
    if route is not None:
        result["map_route"] = {
            "pair": [list(p) for p in route.pair],
            "alternatives": [
                {
                    "profile": a.profile,
                    "native": a.native.model_dump(mode="json"),
                    "backend": json.loads(a.backend_json),
                }
                for a in route.alternatives
            ],
            "endpoint_labels": [list(names) for names in route.endpoint_labels],
        }
    return result


def _page_outcome(
    spec: NavigationSpec, page: Any, site_origin: str
) -> NavigationOutcome:
    if isinstance(page, dict):
        block = page.get("navigation_policy_block")
        if isinstance(block, dict) and isinstance(block.get("blocked_origin"), str):
            try:
                blocked = urlsplit(block["blocked_origin"])
            except ValueError:
                blocked = urlsplit("")
            origin = urlsplit(site_origin)
            if (
                page.get("url") == "chrome-error://chromewebdata/"
                and page.get("error_page") is True
                and page.get("login_page") is False
                and block.get("document_url") == page["url"]
                and block.get("source") == "local_network_policy"
                and block.get("reason") == "outside_declared_local_services"
                and blocked.scheme in ("http", "https")
                and blocked.netloc
                and (blocked.scheme, blocked.netloc) != (origin.scheme, origin.netloc)
            ):
                return NavigationOutcome(
                    "failure",
                    0.0,
                    (
                        ("correct_site", False),
                        ("page_valid", False),
                        ("local_navigation_block_recorded", True),
                    ),
                    "Actor terminated on the browser error document after a recorded navigation outside declared local services.",
                )
    required = (
        "url",
        "http_status",
        "heading_texts",
        "title",
        "login_page",
        "error_page",
    )
    if not isinstance(page, dict) or any(
        k not in page or page[k] is None for k in required
    ):
        return NavigationOutcome("unknown", None, (), "Incomplete final-page capture")
    if (
        type(page["http_status"]) is not int
        or not isinstance(page["heading_texts"], list)
        or any(not isinstance(v, str) for v in page["heading_texts"])
        or not isinstance(page["title"], str)
        or any(type(page[k]) is not bool for k in ("login_page", "error_page"))
    ):
        return NavigationOutcome("unknown", None, (), "Malformed final-page capture")
    if (
        not isinstance(page["url"], str)
        or page["http_status"] < 200
        or page["http_status"] >= 500
    ):
        return NavigationOutcome(
            "unknown", None, (), "Transport or server failure; not an actor failure"
        )
    actual, origin = urlsplit(page["url"]), urlsplit(site_origin)
    expected = spec.completion
    checks = {
        "correct_site": (actual.scheme, actual.netloc)
        == (origin.scheme, origin.netloc),
        "page_valid": 200 <= page["http_status"] < 300
        and not page["login_page"]
        and not page["error_page"],
        "target_path": bool(re.fullmatch(expected.path_regex, unquote(actual.path))),
        "target_heading": any(
            re.search(expected.heading_regex, h, re.I) is not None
            for h in page["heading_texts"]
        ),
    }
    if (
        expected.map_route is not None
        and checks["page_valid"]
        and (page.get("map_route") or {}).get("loading")
    ):
        return NavigationOutcome(
            "unknown",
            None,
            tuple(checks.items()),
            "Native route still loading at termination.",
        )
    if not all(checks.values()):
        return NavigationOutcome(
            "failure",
            0.0,
            tuple(checks.items()),
            "A mandatory final-page identity or validity condition failed.",
        )
    if expected.map_route is not None:
        try:
            checks.update(
                route_checks(
                    original_completion(expected)["map_route"],
                    page.get("map_route"),
                    page["url"],
                )
            )
        except (ValueError, KeyError, TypeError) as error:
            return NavigationOutcome(
                "unknown",
                None,
                tuple(checks.items()),
                "Map route capture/reference error: " + str(error),
            )
    success = all(checks.values())
    return NavigationOutcome(
        "success" if success else "failure", float(success), tuple(checks.items()), None
    )


def navigation_outcome(
    spec: NavigationSpec,
    page: Any,
    *,
    site_origin: str,
    runtime_error: bool,
    selected_records_unchanged: bool,
) -> NavigationOutcome:
    spec = NavigationSpec.model_validate(spec)
    if type(runtime_error) is not bool or type(selected_records_unchanged) is not bool:
        raise TypeError("Exact runtime-error and original protection facts required")
    origin = urlsplit(site_origin)
    if (
        origin.scheme != "http"
        or origin.hostname != "127.0.0.1"
        or origin.port is None
        or not 1024 <= origin.port <= 65535
        or site_origin != f"http://127.0.0.1:{origin.port}"
    ):
        raise ValueError("Original allocated local navigation origin required")
    if runtime_error:
        return NavigationOutcome(
            "unknown",
            None,
            (),
            "Runtime error prevents reliable terminal evaluation",
            version=None,
        )
    result = _page_outcome(spec, page, site_origin)
    if selected_records_unchanged:
        return result
    if result.status == "failure":
        return replace(
            result,
            selected_records_unchanged=False,
            state_change_requires_review=True,
            reason="Terminal goal conditions failed; protected records also changed and require attribution review",
        )
    return NavigationOutcome(
        "unknown",
        None,
        result.checks,
        "Protected records changed; nominal completion requires state review",
        version=None,
        selected_records_unchanged=False,
        state_change_requires_review=True,
    )
