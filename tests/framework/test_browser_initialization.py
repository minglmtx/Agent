"""Setup contracts, no credential fallback, once-only behavior and failure facts."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_initialization import AdminProductInitialization
from lab_generate_skill.sites.shopping_admin.browser_initialization import (
    AdminProductBrowserInitializer,
)
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.browsergym import login_catalog
from browser_worker_fixtures import configuration
from browser_initialization_fixtures import selection, task, Page
from browsergym_fixtures import spec
from test_slurm_commands import guard


def test_fixed_public_selection_does_not_load_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any) -> Any:
        pytest.fail("Public navigation must not access login source")

    monkeypatch.setattr(login_catalog, "admin_login", forbidden)
    assert isinstance(browser_initializer(configuration()), NavigatePublicTask)


def test_admin_configuration_and_factory_preserve_private_refs() -> None:
    original = spec()
    public = task()
    session = BrowserSessionSpec.model_validate(
        {
            **original.model_dump(),
            "task": public,
            "scope": original.scope.model_copy(update={"task": public.identity}),
        }
    )
    value = BrowserWorkerConfiguration.model_validate(
        {**configuration().model_dump(), "spec": session, "initialization": selection()}
    )
    assert isinstance(browser_initializer(value), AdminProductBrowserInitializer)
    assert "password" not in value.model_dump_json()
    assert value.initialization == selection()


@pytest.mark.parametrize(
    "change", ["old_version", "missing", "null", "unknown", "extra"]
)
def test_configuration_requires_explicit_current_initialization(change: str) -> None:
    values = configuration().model_dump()
    if change == "old_version":
        values["schema_version"] = "browser-worker-configuration/1"
    elif change == "missing":
        values.pop("initialization")
    elif change == "null":
        values["initialization"] = None
    elif change == "unknown":
        values["initialization"] = {"kind": "dynamic-module"}
    else:
        values["initialization"] = {
            "kind": "public_navigation",
            "password": "forbidden",
        }
    with pytest.raises(ValidationError):
        BrowserWorkerConfiguration.model_validate(values)


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "http://other:12345/admin",
        "http://127.0.0.1/admin",
        "http://user@127.0.0.1:12345/admin",
        "http://127.0.0.1:12345/admin/",
        "http://127.0.0.1:12345/admin?x=1",
        "https://127.0.0.1:12345/admin",
        "http://127.0.0.1:80/admin",
    ],
)
def test_endpoint_must_be_original_private_admin(endpoint: str) -> None:
    with pytest.raises(ValueError):
        AdminProductInitialization.model_validate(
            {**selection().model_dump(), "endpoint": endpoint}
        )


@pytest.mark.parametrize("field", ["prepared_ref", "site_ref"])
def test_private_reference_scope_is_not_optional(field: str) -> None:
    data = selection().model_dump()
    data[field]["visibility"] = "public"
    with pytest.raises(ValidationError):
        AdminProductInitialization.model_validate(data)


def test_login_setup_routes_before_login_and_returns_no_observation() -> None:
    page = Page()
    setup = AdminProductBrowserInitializer(
        selection(), lambda c: ("user", "private-password")
    )
    setup.setup(page, task(), guard(30))
    assert page.calls[:2] == ["route", "new_page"]
    assert page.login.calls == [
        "goto",
        "Username",
        "fill",
        "Password",
        "fill",
        "click",
        "wait",
        "close",
    ]
    assert page.calls[2:] == ["goto", "selector", "selector", "selector"]
    assert page.url == task().start_url
    prior = page.calls.copy()
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task(), guard(30))
    assert page.calls == prior
    actions: list[str] = []
    for url in [
        "http://127.0.0.1:12345/admin",
        "https://external.invalid/x",
        "http://127.0.0.1:12346/admin",
    ]:
        route = SimpleNamespace(
            request=SimpleNamespace(url=url),
            continue_=lambda: actions.append("allow"),
            abort=lambda: actions.append("block"),
        )
        page.callback(route)
    assert actions == ["allow", "block", "block"]


@pytest.mark.parametrize("failure", ["goto", "fill", "click", "wait"])
def test_login_failure_closes_private_tab_and_does_not_navigate_task(
    failure: str,
) -> None:
    page = Page()
    page.login.failure = failure
    setup = AdminProductBrowserInitializer(selection(), lambda c: ("u", "p"))
    with pytest.raises(RuntimeError, match="fault-"):
        setup.setup(page, task(), guard(30))
    assert page.login.calls[-1] == "close" and "goto" not in page.calls
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task(), guard(30))


def test_failed_login_and_close_preserve_both_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Page()

    def broken(name: str) -> None:
        if name in ("fill", "close"):
            raise RuntimeError(name)

    monkeypatch.setattr(page.login, "event", broken)
    with pytest.raises(BaseExceptionGroup) as caught:
        AdminProductBrowserInitializer(selection(), lambda c: ("u", "p")).setup(
            page, task(), guard(30)
        )
    assert [str(e) for e in caught.value.exceptions] == ["fill", "close"]


def test_logged_out_final_page_rejected() -> None:
    page = Page()
    page.logged_out = True
    with pytest.raises(RuntimeError, match="did not complete"):
        AdminProductBrowserInitializer(selection(), lambda c: ("u", "p")).setup(
            page, task(), guard(30)
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:12346/admin/catalog/product/edit/id/2041/store/0/",
        "http://127.0.0.1:12345/catalog/product/edit/id/2041/store/0/",
        "http://127.0.0.1:12345/admin/catalog/product/edit/id/x/store/0/",
    ],
)
def test_wrong_start_rejected_before_login_or_page_effect(url: str) -> None:
    page = Page()
    setup = AdminProductBrowserInitializer(
        selection(), lambda c: pytest.fail("No credential access")
    )
    with pytest.raises(ValueError):
        setup.setup(page, task().model_copy(update={"start_url": url}), guard(30))
    assert not page.calls and not setup.attempted


def test_expired_control_prevents_login_and_page_effect() -> None:
    class Stopped:
        def checkpoint(self) -> float:
            raise RuntimeError("cancelled")

        def wait(self, seconds: float) -> None:
            raise RuntimeError("cancelled")

    page = Page()
    setup = AdminProductBrowserInitializer(
        selection(), lambda c: pytest.fail("No credential access")
    )
    with pytest.raises(RuntimeError, match="cancelled"):
        setup.setup(page, task(), Stopped())
    assert not page.calls and not setup.attempted


def test_frozen_catalog_can_be_read_without_env_or_new_files() -> None:
    user, password = login_catalog.admin_login(guard(5))
    assert bool(user) and bool(password)


def test_changed_login_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "catalog.py"
    path.write_text("ACCOUNTS = {}")
    monkeypatch.setattr(login_catalog, "CATALOG", path)
    with pytest.raises(ValueError, match="differs"):
        login_catalog.admin_login(guard(5))


def test_wrong_family_rejected_before_credentials() -> None:
    public = task()
    foreign = public.model_copy(
        update={"identity": public.identity.model_copy(update={"family": "other"})}
    )
    page = Page()
    with pytest.raises(ValueError, match="family"):
        AdminProductBrowserInitializer(
            selection(), lambda c: pytest.fail("No login access")
        ).setup(page, foreign, guard(10))
    assert not page.calls


def test_wrong_product_redirect_is_not_a_ready_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Page()

    def wrong(url: str, **kwargs: Any) -> None:
        page.url = url.replace("/id/2041/", "/id/2042/")

    monkeypatch.setattr(page, "goto", wrong)
    with pytest.raises(RuntimeError, match="original product"):
        AdminProductBrowserInitializer(selection(), lambda c: ("u", "p")).setup(
            page, task(), guard(10)
        )
    assert page.login.calls[-1] == "close"


@pytest.mark.parametrize("fault", ["missing", "symlink", "oversize"])
def test_unavailable_or_unbounded_login_source_has_no_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path = tmp_path / "catalog.py"
    if fault == "symlink":
        path.symlink_to(login_catalog.CATALOG)
    elif fault == "oversize":
        path.write_bytes(b"x" * 16385)
    monkeypatch.setattr(login_catalog, "CATALOG", path)
    with pytest.raises(ValueError):
        login_catalog.admin_login(guard(5))
