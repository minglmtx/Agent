"""Original selected71 exact route/heading predicates; data only, no page I/O."""

import html
import re
from urllib.parse import urlsplit
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationPage,
    AdminNavigationSpec,
)


def navigation_checks(
    spec: AdminNavigationSpec, page: AdminNavigationPage, site_netloc: str
) -> dict[str, bool]:
    spec = AdminNavigationSpec.model_validate(spec)
    page = AdminNavigationPage.model_validate(page)
    if (
        type(site_netloc) is not str
        or not site_netloc
        or any(c in site_netloc for c in ("/", "@", "?", "#"))
    ):
        raise ValueError("Original allocated Admin netloc required")
    path = urlsplit(page.url).path
    pattern = (
        "(?:"
        + re.escape("/admin" + spec.target_path.rstrip("/"))
        + r")(?:/index)?(?:/key/[^/]+)?/?"
    )
    heading = re.sub(
        r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", page.heading))
    ).strip()
    return {
        "same_local_deployment": urlsplit(page.url).netloc == site_netloc,
        "valid_authenticated_page": not (page.login or page.page_error),
        "target_page_url": bool(re.fullmatch(pattern, path)),
        "target_page_heading": heading.casefold() == spec.heading.casefold(),
    }
