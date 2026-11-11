"""Customer setup contracts and scoped faults; DOM fixtures are synthetic."""

from typing import Any
from types import SimpleNamespace
import pytest
from lab_generate_skill.domain.browser_initialization import ShoppingOrderInitialization
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.sites.shopping.browser_initialization import (
    ShoppingOrderBrowserInitializer,
)
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.adapters.browsergym import login_catalog
from browser_initialization_fixtures import Page as AdminPage
from test_shopping_order_eta_inputs import public_task
from test_core_contracts import reference
from test_slurm_commands import guard
from browser_worker_fixtures import configuration
from browsergym_fixtures import spec


def selection() -> ShoppingOrderInitialization:
    return ShoppingOrderInitialization(
        endpoint="http://127.0.0.1:18080/",
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
    )


class Page(AdminPage):
    account = "private-user@example.test"

    def __init__(self, context: Any = None) -> None:
        super().__init__(context)
        if context is None:
            self.login = Page(self)

    def wait_for_function(self, script: str, **kwargs: Any) -> None:
        assert "document.cookie" in script and "fields.length===1" in script
        self.event("form_ready")

    def locator(self, selector: str) -> Any:
        if "box-information" in selector:
            return SimpleNamespace(inner_text=lambda **kw: self.account)
        return self


def test_shopping_configuration_uses_fixed_initializer_without_reading_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(control: Any) -> Any:
        pytest.fail("Construction cannot read credentials")

    monkeypatch.setattr(login_catalog, "shopping_login", forbidden)
    public = public_task()
    original = spec(public.start_url)
    session = BrowserSessionSpec.model_validate(
        {
            **original.model_dump(),
            "task": public,
            "scope": original.scope.model_copy(update={"task": public.identity}),
        }
    )
    config = BrowserWorkerConfiguration.model_validate(
        {**configuration().model_dump(), "spec": session, "initialization": selection()}
    )
    assert isinstance(browser_initializer(config), ShoppingOrderBrowserInitializer)
    assert "password" not in config.model_dump_json()


def test_original_customer_setup_closes_login_tab_routes_locally_and_is_once_only() -> (
    None
):
    page = Page()
    setup = ShoppingOrderBrowserInitializer(
        selection(), lambda c: ("private-user@example.test", "private-password")
    )
    setup.setup(page, public_task(), guard(30))
    assert page.calls[:2] == ["route", "new_page"] and page.login.calls == [
        "goto",
        "form_ready",
        "fill",
        "fill",
        "click",
        "selector",
        "close",
    ]
    assert page.url == public_task().start_url
    assert "private-password" not in repr(page.calls + page.login.calls)
    before = page.calls.copy()
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard(30))
    assert page.calls == before
    actions = []
    for url in [
        "http://127.0.0.1:18080/customer/account/",
        "http://127.0.0.1:18081/",
        "https://external.invalid/",
        "file:///tmp/file",
    ]:
        page.callback(
            SimpleNamespace(
                request=SimpleNamespace(url=url),
                continue_=lambda: actions.append("allow"),
                abort=lambda: actions.append("block"),
            )
        )
    assert actions == ["allow", "block", "block", "block"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://remote:18080/",
        "http://127.0.0.1/",
        "https://127.0.0.1:18080/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:18080/admin",
        "http://127.0.0.1:18080/?x=1",
        "http://127.0.0.1:18080/#x",
    ],
)
def test_endpoint_is_exact_allocated_root(endpoint: str) -> None:
    with pytest.raises(ValueError):
        ShoppingOrderInitialization.model_validate(
            {**selection().model_dump(), "endpoint": endpoint}
        )


@pytest.mark.parametrize(
    "change", ["prepared_ref", "site_ref", "family", "origin", "route"]
)
def test_reference_and_task_binding_rejected_before_login(change: str) -> None:
    if change in ("prepared_ref", "site_ref"):
        values = selection().model_dump()
        values[change]["visibility"] = "public"
        with pytest.raises(ValueError):
            ShoppingOrderInitialization.model_validate(values)
        return
    task = public_task()
    if change == "family":
        task = task.model_copy(
            update={"identity": task.identity.model_copy(update={"family": "other"})}
        )
    elif change == "origin":
        task = task.model_copy(
            update={"start_url": "http://127.0.0.1:18081/customer/account/"}
        )
    else:
        task = task.model_copy(
            update={"start_url": "http://127.0.0.1:18080/checkout/cart/"}
        )

    def forbidden(control: Any) -> Any:
        pytest.fail("Invalid binding cannot access credentials")

    page = Page()
    setup = ShoppingOrderBrowserInitializer(selection(), forbidden)
    with pytest.raises(ValueError):
        setup.setup(page, task, guard(30))
    assert not page.calls


@pytest.mark.parametrize("failure", ["goto", "form_ready", "fill", "click", "selector"])
def test_setup_failure_closes_original_tab_and_does_not_navigate_task(
    failure: str,
) -> None:
    page = Page()
    page.login.failure = failure
    setup = ShoppingOrderBrowserInitializer(
        selection(), lambda c: ("private-user@example.test", "p")
    )
    with pytest.raises(RuntimeError, match="fault-"):
        setup.setup(page, public_task(), guard(30))
    assert page.login.calls[-1] == "close" and "goto" not in page.calls
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard(30))


@pytest.mark.parametrize("case", ["wrong_customer", "logged_out", "close_and_login"])
def test_wrong_account_and_joint_login_cleanup_failure_remain_errors(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = Page()
    setup = ShoppingOrderBrowserInitializer(
        selection(), lambda c: ("private-user@example.test", "p")
    )
    if case == "wrong_customer":
        page.account = "other-customer@example.test"
    elif case == "logged_out":
        page.logged_out = True
    else:

        def broken(name: str) -> None:
            page.login.calls.append(name)
            if name in ("fill", "close"):
                raise RuntimeError(name)

        monkeypatch.setattr(page.login, "event", broken)
    if case == "close_and_login":
        with pytest.raises(BaseExceptionGroup) as caught:
            setup.setup(page, public_task(), guard(30))
        assert [str(e) for e in caught.value.exceptions] == ["fill", "close"]
    else:
        with pytest.raises(RuntimeError):
            setup.setup(page, public_task(), guard(30))
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard(30))
