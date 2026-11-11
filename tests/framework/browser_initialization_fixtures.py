"""DOM-shaped fixture for setup ordering/faults, not browser acceptance."""

from typing import Any
from lab_generate_skill.domain.browser_initialization import AdminProductInitialization
from test_core_contracts import reference
from test_admin_description_inputs import public_task


def selection() -> AdminProductInitialization:
    return AdminProductInitialization(
        endpoint="http://127.0.0.1:12345/admin",
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
    )


def task() -> Any:
    return public_task(
        start_url="http://127.0.0.1:12345/admin/catalog/product/edit/id/2041/store/0/"
    )


class Page:
    def __init__(self, context: Any = None) -> None:
        self.context = context or self
        self.calls: list[str] = []
        self.login = self if context is not None else Page(self)
        self.url = ""
        self.failure: str | None = None
        self.logged_out = False
        self.callback: Any = None

    def event(self, name: str) -> None:
        self.calls.append(name)
        if name == self.failure:
            raise RuntimeError("fault-" + name)

    def route(self, pattern: str, callback: Any) -> None:
        self.event("route")
        self.callback = callback

    def new_page(self) -> Any:
        self.event("new_page")
        return self.login

    def goto(self, url: str, **kwargs: Any) -> None:
        self.event("goto")
        self.url = url

    def get_by_label(self, name: str) -> Any:
        self.event(name)
        return self

    def get_by_role(self, *args: Any, **kwargs: Any) -> Any:
        return self

    def fill(self, value: str, **kwargs: Any) -> None:
        self.event("fill")

    def click(self, **kwargs: Any) -> None:
        self.event("click")

    def locator(self, value: str) -> Any:
        return self

    def wait_for(self, **kwargs: Any) -> None:
        self.event("wait")

    def wait_for_selector(self, value: str, **kwargs: Any) -> None:
        self.event("selector")

    def count(self) -> int:
        return int(self.logged_out)

    def close(self) -> None:
        self.event("close")
