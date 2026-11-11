"""Selected actual MapData XHR selector; exports and other requests stay native."""

from urllib.parse import parse_qs, urlsplit
from typing import Any


def selected_bounds(
    origin: str, url: object, method: object, resource_type: object
) -> tuple[str, ...] | None:
    """Select raw request metadata; NativeExchange validates before HTTP.

    Keep malformed selected bbox strings so the collector can retain their
    original URL before the execution boundary rejects them.
    """
    if not all(isinstance(v, str) for v in (url, method, resource_type)):
        raise ValueError("Actual browser request metadata must be text")
    assert isinstance(url, str)
    original, actual = urlsplit(origin), urlsplit(url)
    if (
        method != "GET"
        or resource_type != "xhr"
        or (actual.scheme, actual.netloc) != (original.scheme, original.netloc)
        or actual.path != "/api/0.6/map"
        or actual.fragment
    ):
        return None
    query = parse_qs(actual.query, keep_blank_values=True)
    if set(query) != {"bbox"} or len(query["bbox"]) != 1:
        return None
    raw = tuple(query["bbox"][0].split(","))
    return raw


def private_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
    ):
        raise ValueError("Actual browser header mapping required")
    result = {
        k: v
        for k, v in value.items()
        if k.lower()
        not in (
            "referer",
            "cookie",
            "authorization",
            "proxy-authorization",
        )
    }
    # Omitting this leaves Chromium's cached referrer intact on URL override.
    result["referer"] = ""
    return result
