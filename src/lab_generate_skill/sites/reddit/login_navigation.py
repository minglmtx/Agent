"""Recognize the original Postmill CookieCheckingListener redirect only."""

import re
from typing import Any
from urllib.parse import urlsplit


def original_login_document(
    response: Any, current_url: str, requested_url: str
) -> bool:
    """Read returned request metadata; no requests, cookie writes, or retries."""
    if (
        response is None
        or type(response.status) is not int
        or not 200 <= response.status < 300
    ):
        return False
    if current_url == requested_url:
        return True
    actual, expected = urlsplit(current_url), urlsplit(requested_url)
    if (
        expected.path != "/login"
        or expected.query
        or expected.fragment
        or (actual.scheme, actual.netloc, actual.path)
        != (expected.scheme, expected.netloc, expected.path)
        or actual.fragment
        or re.fullmatch(r"_cookie_check=[1-9][0-9]{0,18}", actual.query) is None
    ):
        return False
    previous = response.request.redirected_from
    if (
        previous is None
        or previous.url != requested_url
        or previous.redirected_from is not None
    ):
        return False
    redirect = previous.response()
    return (
        redirect is not None
        and type(redirect.status) is int
        and redirect.status == 302
        and redirect.headers.get("location") == current_url
    )
