"""Original category path/heading/health semantics, without browser or I/O."""

import re
from urllib.parse import unquote, urlsplit
from .navigation_page import CategoryNavigationPage
from .navigation_spec import CategoryNavigationSpec

CHECKS = ("correct_site", "page_valid", "target_path", "target_heading")


class IncompleteCategoryNavigation(ValueError):
    pass


def category_navigation_checks(
    spec: CategoryNavigationSpec, page: CategoryNavigationPage, site_origin: str
) -> dict[str, bool]:
    spec = CategoryNavigationSpec.model_validate(spec)
    page = CategoryNavigationPage.model_validate(page)
    origin, actual = urlsplit(site_origin), urlsplit(page.health.url)
    if (
        origin.scheme not in ("http", "https")
        or not origin.netloc
        or origin.username is not None
        or origin.password is not None
        or origin.query
        or origin.fragment
        or origin.path not in ("", "/")
    ):
        raise ValueError("Declared category site origin required")
    block = page.navigation_policy_block
    if (
        block is not None
        and page.health.url == block.document_url
        and page.health.error_page
        and not page.health.login_page
    ):
        blocked = urlsplit(block.blocked_origin)
        if (
            blocked.scheme in ("http", "https")
            and blocked.netloc
            and (
                blocked.scheme,
                blocked.netloc,
            )
            != (origin.scheme, origin.netloc)
        ):
            return {
                "correct_site": False,
                "page_valid": False,
                "local_navigation_block_recorded": True,
            }
    status = page.health.http_status
    if (
        page.document_ready != "complete"
        or status is None
        or status < 200
        or status >= 500
    ):
        raise IncompleteCategoryNavigation(
            "Incomplete/changed category document or transport/server failure"
        )
    expected = spec.original.completion
    return {
        "correct_site": (actual.scheme, actual.netloc)
        == (origin.scheme, origin.netloc),
        "page_valid": 200 <= status < 300
        and not page.health.login_page
        and not page.health.error_page,
        "target_path": re.fullmatch(expected.path_regex, unquote(actual.path))
        is not None,
        "target_heading": any(
            re.search(expected.heading_regex, heading, re.I) is not None
            for heading in page.heading_texts
        ),
    }
