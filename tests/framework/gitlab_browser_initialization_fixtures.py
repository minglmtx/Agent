"""Explicit DOM-shaped setup fixture, never original GitLab evidence."""

from typing import Any
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from browser_initialization_fixtures import Page as BasePage
from test_core_contracts import reference


def selection() -> GitlabSshKeyInitialization:
    return GitlabSshKeyInitialization(
        endpoint="http://127.0.0.1:18080/",
        native_account_id=17,
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
    )


class Page(BasePage):
    login: "Page"

    def __init__(self, context: Any = None) -> None:
        super().__init__(context)
        self.account_id: object = 17
        self.close_error = False
        self.selectors: list[str] = []
        if context is None:
            self.login = Page(self)

    def wait_for_function(self, script: str, **kwargs: Any) -> None:
        self.event("form_ready" if "authenticity_token" in script else "account_ready")

    def evaluate(self, script: str) -> object:
        assert script == "() => window.gon.current_user_id"
        self.event("account_id")
        return self.account_id

    def locator(self, selector: str) -> Any:
        self.selectors.append(selector)
        return self

    def close(self) -> None:
        super().close()
        if self.close_error:
            raise OSError("original login tab close failed")
