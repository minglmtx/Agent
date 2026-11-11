"""DOM-shaped Postmill setup fixture; not native website evidence."""

from types import SimpleNamespace
from typing import Any
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from browser_initialization_fixtures import Page as BasePage
from test_browser_task_files_actual import frozen
from test_core_contracts import reference


def selection() -> RedditNativeImageInitialization:
    return RedditNativeImageInitialization(
        endpoint="http://127.0.0.1:18080/",
        native_account_id=17,
        native_account_username="native-user",
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
        task_files=reddit_photo_plan(
            frozen().scope, "/tmp/engineering-reddit/browser-uploads"
        ),
    )


def task() -> Any:
    return frozen("http://127.0.0.1:18080/submit").task


class Page(BasePage):
    login: "Page"

    def __init__(self, context: Any = None) -> None:
        super().__init__(context)
        self.account: object = "native-user"
        self.status: object = 200
        self.close_error = False
        self.selectors: list[str] = []
        if context is None:
            self.login = Page(self)

    def goto(self, url: str, **kwargs: Any) -> Any:
        super().goto(url, **kwargs)
        return SimpleNamespace(status=self.status)

    def wait_for_function(self, script: str, **kwargs: Any) -> None:
        self.event(
            "form_ready"
            if "_csrf_token" in script
            else (
                "submission_ready" if "submission[image]" in script else "account_ready"
            )
        )

    def evaluate(self, script: str) -> object:
        self.event("account_name")
        return self.account

    def locator(self, selector: str) -> Any:
        self.selectors.append(selector)
        return self

    def close(self) -> None:
        super().close()
        if self.close_error:
            raise OSError("original login tab close failed")
