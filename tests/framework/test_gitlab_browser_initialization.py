"""Selected root/login contracts, input boundaries and original failure retention."""

from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.browser_capture import browser_collector
from lab_generate_skill.sites.gitlab.page_capture import GitlabPageHealthCollector
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.gitlab.browser_initialization import (
    GitlabSshKeyBrowserInitializer,
    FORM,
)
from lab_generate_skill.adapters.browsergym import login_catalog
from browser_worker_fixtures import configuration
from browsergym_fixtures import spec
from gitlab_browser_initialization_fixtures import Page, selection
from test_gitlab_ssh_key_inputs import public_task
from test_slurm_commands import guard


def test_fixed_dispatch_and_canonical_repeat_are_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        login_catalog,
        "gitlab_login",
        lambda c: pytest.fail("Construction cannot read credentials"),
    )
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
    assert (
        BrowserWorkerConfiguration.model_validate_json(config.model_dump_json())
        == config
    )
    assert isinstance(browser_initializer(config), GitlabSshKeyBrowserInitializer)
    assert isinstance(browser_collector(config), GitlabPageHealthCollector)
    assert "password" not in config.model_dump_json()


def test_original_account_setup_closes_private_tab_and_retains_public_root_once() -> (
    None
):
    page = Page()
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    setup.setup(page, public_task(), guard(30))
    assert page.calls == ["route", "new_page", "goto", "account_ready", "account_id"]
    assert page.login.calls == [
        "goto",
        "form_ready",
        "fill",
        "fill",
        "click",
        "account_ready",
        "account_id",
        "close",
    ]
    assert page.url == public_task().start_url
    assert all(s.startswith(FORM) for s in page.login.selectors)
    assert "private-password" not in repr(page.calls + page.login.calls)
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard(30))
    actions: list[str] = []
    for url in (
        "http://127.0.0.1:18080/",
        "http://127.0.0.1:18081/",
        "https://external.invalid/",
        "file:///tmp/file",
    ):
        page.callback(
            SimpleNamespace(
                request=SimpleNamespace(url=url),
                continue_=lambda: actions.append("allow"),
                abort=lambda: actions.append("block"),
            )
        )
    assert actions == ["allow", "block", "block", "block"]


@pytest.mark.parametrize("port", [1024, 65535])
def test_endpoint_port_boundaries(port: int) -> None:
    value = GitlabSshKeyInitialization.model_validate(
        {**selection().model_dump(), "endpoint": f"http://127.0.0.1:{port}/"}
    )
    value.check_task(public_task(start_url=value.endpoint))


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        1,
        [],
        "http://remote:18080/",
        "http://127.0.0.1/",
        "https://127.0.0.1:18080/",
        "http://127.0.0.1:1023/",
        "http://127.0.0.1:65536/",
        "http://user@127.0.0.1:18080/",
        "http://127.0.0.1:18080/-/profile/keys",
        "http://127.0.0.1:18080/?x=1",
        "http://127.0.0.1:18080/#x",
        "x" * 4097,
    ],
)
def test_invalid_endpoint_denied(value: Any) -> None:
    with pytest.raises(ValueError):
        GitlabSshKeyInitialization.model_validate(
            {**selection().model_dump(), "endpoint": value}
        )


@pytest.mark.parametrize("value", [None, True, "17", 0, -1, [], 2**63, 10**300])
def test_invalid_native_account_pin_denied(value: Any) -> None:
    with pytest.raises(ValueError):
        GitlabSshKeyInitialization.model_validate(
            {**selection().model_dump(), "native_account_id": value}
        )


@pytest.mark.parametrize("field", ["prepared_ref", "site_ref"])
def test_public_or_wrong_private_reference_denied(field: str) -> None:
    original = getattr(selection(), field)
    for change in (
        {"visibility": "public"},
        {"content_schema": "wrong/1"},
        {"media_type": "text/plain"},
    ):
        with pytest.raises(ValueError):
            GitlabSshKeyInitialization.model_validate(
                {**selection().model_dump(), field: original.model_copy(update=change)}
            )


@pytest.mark.parametrize("change", ["family", "split", "route", "port"])
def test_foreign_task_is_rejected_before_credentials(change: str) -> None:
    task = public_task()
    if change in ("family", "split"):
        task = task.model_copy(
            update={
                "identity": task.identity.model_copy(
                    update={change: "other" if change == "family" else "test"}
                )
            }
        )
    else:
        task = task.model_copy(
            update={
                "start_url": (
                    "http://127.0.0.1:18080/-/profile/keys"
                    if change == "route"
                    else "http://127.0.0.1:18081/"
                )
            }
        )
    page = Page()
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: pytest.fail("No credential access")
    )
    with pytest.raises(ValueError):
        setup.setup(page, task, guard())
    assert not page.calls and not setup.attempted


@pytest.mark.parametrize(
    "failure",
    ["goto", "form_ready", "fill", "click", "account_ready", "account_id", "close"],
)
def test_original_login_fault_closes_tab_and_cannot_repeat(failure: str) -> None:
    page = Page()
    page.login.failure = failure
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    with pytest.raises(RuntimeError, match="fault-" + failure):
        setup.setup(page, public_task(), guard())
    assert page.login.calls[-1] == "close" and page.calls == ["route", "new_page"]
    old = page.login.calls.copy()
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, public_task(), guard())
    assert page.login.calls == old


@pytest.mark.parametrize("account", [None, True, "17", 18])
@pytest.mark.parametrize("tab", ["login", "root"])
def test_wrong_or_untyped_native_account_is_not_ready(account: Any, tab: str) -> None:
    page = Page()
    target = page.login if tab == "login" else page
    target.account_id = account
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    with pytest.raises(RuntimeError, match="original native account"):
        setup.setup(page, public_task(), guard())
    assert page.login.calls[-1] == "close"


def test_primary_and_private_tab_cleanup_fault_are_both_preserved() -> None:
    page = Page()
    page.login.failure = "click"
    page.login.close_error = True
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    with pytest.raises(BaseExceptionGroup) as caught:
        setup.setup(page, public_task(), guard())
    assert [type(e) for e in caught.value.exceptions] == [RuntimeError, OSError]
    assert str(caught.value.exceptions[0]) == "fault-click"


def test_cancel_before_any_effect_does_not_read_credentials() -> None:
    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-setup")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    page = Page()
    setup = GitlabSshKeyBrowserInitializer(
        selection(), lambda c: pytest.fail("No credential access")
    )
    with pytest.raises(OperationStopped):
        setup.setup(page, public_task(), Stopped())
    assert not page.calls and not setup.attempted
