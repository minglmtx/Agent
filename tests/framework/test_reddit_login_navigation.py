"""The original cookie check is an observed redirect, never a relaxed start URL."""

from types import SimpleNamespace as NS
from typing import Any
import pytest
from lab_generate_skill.sites.reddit.login_navigation import original_login_document
from lab_generate_skill.sites.reddit.browser_initialization import (
    RedditNativeImageBrowserInitializer,
)
from reddit_browser_initialization_fixtures import Page, selection, task
from test_slurm_commands import guard

URL = "http://127.0.0.1:18080/login"
FINAL = URL + "?_cookie_check=1793281255"


def response(target: str = FINAL) -> Any:
    old = NS(
        url=URL,
        redirected_from=None,
        response=lambda: NS(status=302, headers={"location": target}),
    )
    return NS(status=200, request=NS(redirected_from=old))


def test_original_direct_and_cookie_redirect() -> None:
    assert original_login_document(NS(status=200), URL, URL)
    assert original_login_document(response(), FINAL, URL)


@pytest.mark.parametrize(
    "url",
    [
        URL + "?_cookie_check=0",
        URL + "?_cookie_check=-1",
        URL + "?_cookie_check=01",
        URL + "?_cookie_check=1.0",
        URL + "?_cookie_check=",
        URL + "?_cookie_check=true",
        URL + "?_cookie_check=" + "9" * 20,
        URL + "?_cookie_check=1&next=/submit",
        URL + "?_cookie_check=1&_cookie_check=2",
        FINAL + "#fragment",
        FINAL.replace("18080", "18081"),
        FINAL.replace("127.0.0.1", "outside.example"),
        FINAL.replace("/login", "/submit"),
        FINAL.replace("http:", "https:"),
        URL + "?%5Fcookie_check=1",
        URL + "?_cookie_check=1%0a",
    ],
)
def test_other_query_origin_path_or_fragment_is_rejected(url: str) -> None:
    assert not original_login_document(response(url), url, URL)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "wrong_source",
        "extra_hop",
        "no_response",
        "301",
        "location",
        "503",
        "bool_status",
    ],
)
def test_exact_original_redirect_chain_required(case: str) -> None:
    r = response()
    old = r.request.redirected_from
    if case == "missing":
        r.request.redirected_from = None
    elif case == "wrong_source":
        old.url = URL + "?other=1"
    elif case == "extra_hop":
        old.redirected_from = NS(url=URL)
    elif case == "no_response":
        old.response = lambda: None
    elif case == "301":
        old.response = lambda: NS(status=301, headers={"location": FINAL})
    elif case == "location":
        old.response = lambda: NS(status=302, headers={"location": URL})
    elif case == "503":
        r.status = 503
    else:
        r.status = True
    assert not original_login_document(r, FINAL, URL)


@pytest.mark.parametrize("current", [URL, FINAL])
def test_missing_response_never_healthy(current: str) -> None:
    assert not original_login_document(None, current, URL)


def test_cookie_check_does_not_permit_redirected_submit() -> None:
    assert not original_login_document(
        response(), FINAL, "http://127.0.0.1:18080/submit"
    )


def test_original_login_redirect_then_untouched_submit_and_repeat_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Page()
    original = page.login.goto

    def goto(url: str, **kwargs: Any) -> Any:
        original(url, **kwargs)
        page.login.url = FINAL
        return response()

    monkeypatch.setattr(page.login, "goto", goto)
    setup = RedditNativeImageBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    setup.setup(page, task(), guard(5))
    assert page.url == task().start_url
    assert page.login.calls[-1] == "close"
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task(), guard(5))
