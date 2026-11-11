"""Explicit navigation setup, with DOM-shaped doubles and no task permission."""

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import pytest
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.sites.shopping_admin.navigation_browser_initialization import (
    AdminNavigationBrowserInitializer,
)
from lab_generate_skill.adapters.browsergym import login_catalog
from browser_worker_fixtures import configuration
from browser_initialization_fixtures import Page
from test_core_contracts import reference
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def selection(native: Any, ref: Any, public: Any) -> AdminNavigationInitialization:
    origin = urlsplit(public.start_url)
    return AdminNavigationInitialization(
        endpoint=f"{origin.scheme}://{origin.netloc}/admin",
        prepared_ref=reference(content_schema="prepared-task/1"),
        site_ref=reference(content_schema="site-resource-started/1"),
        native_contract_sha256=ref.sha256,
        start_path=native["spec"]["start_path"],
    )


def configured(native: Any, ref: Any, public: Any) -> BrowserWorkerConfiguration:
    base = configuration()
    spec = base.spec.model_copy(
        update={
            "task": public,
            "scope": base.spec.scope.model_copy(update={"task": public.identity}),
        }
    )
    return BrowserWorkerConfiguration.model_validate(
        {
            **base.model_dump(),
            "spec": spec,
            "initialization": selection(native, ref, public),
        }
    )


def test_all71_explicit_setup_keeps_declared_start_without_target_navigation(
    contracts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        login_catalog, "admin_login", lambda control: ("unit-user", "unit-password")
    )
    for native, ref, public in contracts:
        config = configured(native, ref, public)
        assert "password" not in config.model_dump_json()
        setup = browser_initializer(config)
        assert isinstance(setup, AdminNavigationBrowserInitializer)
        page = Page()
        setup.setup(page, public, guard())
        assert page.url == public.start_url
        assert page.calls == ["route", "new_page", "goto", "selector", "selector"]
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
        with pytest.raises(RuntimeError, match="already attempted"):
            setup.setup(page, public, guard())


@pytest.mark.parametrize(
    "fault",
    [
        "public_navigation",
        "foreign_family",
        "heldout",
        "foreign_start",
        "missing_native_pin",
    ],
)
def test_wrong_declaration_rejected_before_setup(contracts: Any, fault: str) -> None:
    native, ref, public = contracts[0]
    config = configured(native, ref, public)
    data = config.model_dump()
    if fault == "public_navigation":
        data["initialization"] = {"kind": "public_navigation"}
    elif fault == "missing_native_pin":
        data["initialization"].pop("native_contract_sha256")
    elif fault == "foreign_start":
        data["spec"]["task"]["start_url"] = (
            selection(native, ref, public).endpoint + "/other/"
        )
    else:
        field, value = (
            ("family", "product_description")
            if fault == "foreign_family"
            else ("split", "test")
        )
        data["spec"]["task"]["identity"][field] = value
        data["spec"]["scope"]["task"][field] = value
    with pytest.raises(ValueError):
        BrowserWorkerConfiguration.model_validate(data)


@pytest.mark.parametrize("failure", ["goto", "fill", "click", "wait"])
def test_partial_login_closes_private_tab_and_forbids_retry(
    contracts: Any, failure: str
) -> None:
    native, ref, public = contracts[0]
    page = Page()
    page.login.failure = failure
    setup = AdminNavigationBrowserInitializer(
        selection(native, ref, public), lambda control: ("unit", "unit")
    )
    with pytest.raises(RuntimeError, match="fault-"):
        setup.setup(page, public, guard())
    assert page.login.calls[-1] == "close" and "goto" not in page.calls
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public, guard())


@pytest.mark.parametrize("failure", ["logged_out", "foreign_origin", "cancelled"])
def test_setup_never_claims_ready_after_fault(
    contracts: Any, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    native, ref, public = contracts[0]
    page = Page()
    setup = AdminNavigationBrowserInitializer(
        selection(native, ref, public), lambda control: ("unit", "unit")
    )
    if failure == "logged_out":
        page.logged_out = True
    elif failure == "foreign_origin":
        monkeypatch.setattr(
            page,
            "goto",
            lambda *args, **kwargs: setattr(
                page, "url", "http://127.0.0.1:19999/admin/"
            ),
        )

    class Stopped:
        def checkpoint(self) -> float:
            raise RuntimeError("cancelled")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(RuntimeError):
        setup.setup(page, public, Stopped() if failure == "cancelled" else guard())
    assert not setup.attempted if failure == "cancelled" else setup.attempted
    if failure == "cancelled":
        assert not page.calls


def test_navigation_prepared_browser_requires_fixed_checker_before_graph_read(
    tmp_path: Path, contracts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prepared_browser_fixtures import prepared_case

    with prepared_case(tmp_path, monkeypatch) as c:
        native, ref, public = contracts[0]
        endpoint = c.binding.site.instance.endpoint
        public = public.model_copy(
            update={"start_url": endpoint + native["spec"]["start_path"]}
        )
        base = c.browser.spec.configuration
        spec = base.spec.model_copy(
            update={
                "task": public,
                "scope": base.spec.scope.model_copy(update={"task": public.identity}),
            }
        )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": spec,
                "initialization": selection(native, ref, public),
            }
        )
        from lab_generate_skill.domain.browser_resource import BrowserResourceSpec

        browser = BrowserResourceSpec(
            token=c.browser.spec.token, configuration=config, slurm=c.browser.spec.slurm
        )
        with pytest.raises(OwnershipConflict, match="fixed task checks"):
            c.binding.verify(browser, c.browser.op, guard())


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "native_pin",
        "start_path",
        "prepared_ref",
        "endpoint",
        "task",
        "private_input",
        "allocation",
        "action",
    ],
)
def test_fixed_navigation_prepared_checker_retains_original_join(
    tmp_path: Path, contracts: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from prepared_browser_fixtures import prepared_case
    from admin_navigation_fixtures import request
    from lab_generate_skill.sites.shopping_admin.tasks.navigation_prepared_browser import (
        NavigationPreparedBrowserChecks,
    )
    from lab_generate_skill.domain.preparation_record import PreparedPublication

    with prepared_case(tmp_path, monkeypatch) as c:
        native, ref, public = contracts[0]
        endpoint = c.binding.site.instance.endpoint
        public = public.model_copy(
            update={"start_url": endpoint + native["spec"]["start_path"]}
        )
        initialization = selection(native, ref, public).model_copy(
            update={"prepared_ref": c.binding.publication.prepared_ref}
        )
        current = request(
            contracts, action="prepare", operation_id="unit-nav-original-prepare"
        )
        token = c.site.spec.token
        current = current.model_copy(
            update={
                "operation": current.operation.model_copy(
                    update={
                        "run_id": token.owner.run_id,
                        "owner_id": token.owner.owner_id,
                        "allocation_id": token.allocation_id,
                    }
                )
            }
        )
        if fault == "native_pin":
            initialization = initialization.model_copy(
                update={"native_contract_sha256": "f" * 64}
            )
        elif fault == "start_path":
            initialization = initialization.model_copy(update={"start_path": "/other/"})
        elif fault == "prepared_ref":
            initialization = initialization.model_copy(
                update={"prepared_ref": reference(content_schema="prepared-task/1")}
            )
        elif fault == "endpoint":
            initialization = initialization.model_copy(
                update={"endpoint": "http://127.0.0.1:19999/admin"}
            )
        elif fault == "task":
            current = current.model_copy(
                update={"task": current.task.model_copy(update={"task_id": "foreign"})}
            )
        elif fault == "private_input":
            current = current.model_copy(
                update={"private_input": current.private_input + " "}
            )
        elif fault == "allocation":
            current = current.model_copy(
                update={
                    "operation": current.operation.model_copy(
                        update={"allocation_id": "foreign"}
                    )
                }
            )
        elif fault == "action":
            current = current.model_copy(update={"action": "inspect"})
        checks = NavigationPreparedBrowserChecks()
        args = (
            c.binding.publication,
            c.site.spec,
            c.binding.site,
            current,
            initialization,
            guard(),
        )
        if fault == "none":
            checks.check(*args)
        else:
            with pytest.raises(OwnershipConflict):
                checks.check(*args)
