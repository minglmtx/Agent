"""One explicit unit browser leaf for current source engineering compositions."""

from typing import Any
import pytest
import prepared_browser_native
from browser_resource_fixtures import resource_case


def unit_source_browsers(patch: pytest.MonkeyPatch, browsers: list[Any]) -> None:
    def unit_browser(*args: Any, **kwargs: Any) -> Any:
        kwargs["real_step"] = False
        browser = resource_case(*args, **kwargs)
        browsers.append(browser)
        return browser

    patch.setattr(prepared_browser_native, "resource_case", unit_browser)
    patch.setattr(
        prepared_browser_native,
        "EngineeringTreeAuthority",
        lambda store: browsers[-1].authority,
    )
