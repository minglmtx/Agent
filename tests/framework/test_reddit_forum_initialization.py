"""Original forum-directory start, one login, no target selection or extra action."""

from typing import Any
import pytest
from lab_generate_skill.sites.reddit.browser_initialization import (
    RedditNativeImageBrowserInitializer,
)
from lab_generate_skill.sites.reddit.forum_directory_initial import (
    FORUM_DIRECTORY_READY,
)
from reddit_forum_source_fixtures import public, selected
from reddit_browser_initialization_fixtures import Page
from test_slurm_commands import guard


class ForumPage(Page):
    def wait_for_function(self, script: str, **kwargs: Any) -> None:
        if script == FORUM_DIRECTORY_READY:
            self.event("forums_ready")
        else:
            super().wait_for_function(script, **kwargs)


@pytest.mark.parametrize("fault", [None, "goto", "account_ready", "forums_ready"])
def test_forum_start_one_login_no_target_selection_and_no_retry(
    fault: str | None,
) -> None:
    page = ForumPage()
    page.failure = fault
    setup = RedditNativeImageBrowserInitializer(
        selected(), lambda c: ("native-user", "private-password")
    )
    if fault is None:
        setup.setup(page, public(), guard(5))
        assert page.calls == [
            "route",
            "new_page",
            "goto",
            "account_ready",
            "account_name",
            "forums_ready",
        ]
        assert page.url == public().start_url
    else:
        with pytest.raises(RuntimeError, match="fault-"):
            setup.setup(page, public(), guard(5))
    assert page.login.calls[-1] == "close"
    assert not any(x in page.calls for x in ("click", "fill", "submission_ready"))
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public(), guard(5))


@pytest.mark.parametrize(
    "path", ["/submit", "/forums/all?x=1", "/forums/all/", "/f/EarthPorn"]
)
def test_changed_public_start_refused_before_login(path: str) -> None:
    setup = RedditNativeImageBrowserInitializer(
        selected(), lambda c: pytest.fail("Invalid public start cannot read login")
    )
    with pytest.raises(ValueError):
        setup.setup(
            ForumPage(),
            public().model_copy(update={"start_url": "http://127.0.0.1:18080" + path}),
            guard(5),
        )
