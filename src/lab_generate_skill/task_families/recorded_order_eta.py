"""Exact selected legacy query and complete-native integrity decisions."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit
from .typed_answer import parse_answer

CHECKS = (
    "page_valid",
    "requested_records_unchanged",
    "answer_schema",
    "answer_estimated_delivery_date",
    "complete_native_reference_unchanged",
)


@dataclass(frozen=True)
class EtaOutcome:
    status: Literal["success", "failure", "unknown"]
    reward: int | None
    checks: tuple[bool | None, ...]
    reason: str


def decide_eta(
    *,
    before: dict[str, object],
    after: dict[str, object],
    before_core: str,
    after_core: str,
    page_url: str,
    http_status: int | None,
    login_page: bool,
    error_page: bool,
    site_origin: str,
    answer: str | None,
) -> EtaOutcome:
    for reference in (before, after):
        if not isinstance(reference, dict):
            return EtaOutcome(
                "unknown", None, (None,) * 5, "INCOMPLETE_NATIVE_REFERENCE"
            )
        values = reference.get("values")
        if (
            not reference.get("object_id")
            or not isinstance(values, dict)
            or set(values) != {"estimated_delivery_date"}
            or values["estimated_delivery_date"] is None
        ):
            return EtaOutcome(
                "unknown", None, (None,) * 5, "INCOMPLETE_NATIVE_REFERENCE"
            )
    integrity = before == after and before_core == after_core
    if (
        type(page_url) is not str
        or type(login_page) is not bool
        or type(error_page) is not bool
    ):
        return EtaOutcome(
            "unknown",
            None,
            (None, None, None, None, integrity),
            "TERMINAL_PAGE_UNAVAILABLE",
        )
    if type(http_status) is not int or http_status < 200 or http_status >= 500:
        return EtaOutcome(
            "unknown",
            None,
            (None, None, None, None, integrity),
            "TERMINAL_TRANSPORT_UNAVAILABLE",
        )
    current, origin = urlsplit(page_url), urlsplit(site_origin)
    page_valid = (
        200 <= http_status < 300
        and (current.scheme, current.netloc) == (origin.scheme, origin.netloc)
        and not login_page
        and not error_page
    )
    try:
        value = parse_answer(answer)
        schema = set(value) == {"estimated_delivery_date"}
    except (TypeError, ValueError):
        value = {}
        schema = False
    expected = before["values"]
    assert isinstance(expected, dict)
    actual = value.get("estimated_delivery_date")
    same_value = (
        isinstance(actual, str)
        and actual.strip() == str(expected["estimated_delivery_date"]).strip()
    )
    checks = (page_valid, before == after, schema, same_value, integrity)
    success = all(checks)
    return EtaOutcome(
        "success" if success else "failure",
        int(success),
        checks,
        "ALL_CHECKS_PASS" if success else "REQUIRED_CHECK_FAILED",
    )
