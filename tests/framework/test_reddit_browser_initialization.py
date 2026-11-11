"""Current image-family setup dispatch, boundary/privacy/fault and repeat tests."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.browser_task_files import browser_task_files
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.sites.reddit.browser_initialization import (
    RedditNativeImageBrowserInitializer,
    FORM,
)
from lab_generate_skill.adapters.browsergym.task_files import LocalBrowserTaskFiles
from lab_generate_skill.adapters.browsergym import login_catalog
from browser_worker_fixtures import configuration
from reddit_browser_initialization_fixtures import Page, selection, task
from test_browser_task_files_actual import frozen
from test_slurm_commands import guard


def test_fixed_initializer_and_file_factory_are_inert_and_wire_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        login_catalog,
        "reddit_login",
        lambda c: pytest.fail("Construction cannot read credentials"),
    )
    base = configuration().model_dump(mode="json")
    spec = frozen(task().start_url)
    base.update(
        spec=spec.model_dump(mode="json"),
        initialization=selection().model_dump(mode="json"),
    )
    config = BrowserWorkerConfiguration.model_validate_json(json.dumps(base))
    assert (
        BrowserWorkerConfiguration.model_validate_json(config.model_dump_json())
        == config
    )
    assert isinstance(browser_initializer(config), RedditNativeImageBrowserInitializer)
    assert isinstance(browser_task_files(config), LocalBrowserTaskFiles)
    assert not Path(selection().task_files.staging_root).exists()
    assert browser_task_files(configuration()) is None
    assert "password" not in config.model_dump_json()


def test_one_native_login_retains_submit_start_and_closes_private_tab() -> None:
    page = Page()
    setup = RedditNativeImageBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    setup.setup(page, task(), guard(5))
    assert page.calls == [
        "route",
        "new_page",
        "goto",
        "account_ready",
        "account_name",
        "submission_ready",
    ]
    assert page.login.calls == [
        "goto",
        "form_ready",
        "fill",
        "fill",
        "click",
        "account_ready",
        "account_name",
        "close",
    ]
    assert page.url == task().start_url
    assert all(s.startswith(FORM) for s in page.login.selectors)
    assert "private-password" not in repr(page.calls + page.login.calls)
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task(), guard(5))
    actions: list[str] = []
    for url in [
        "http://127.0.0.1:18080/submit",
        "http://127.0.0.1:18081/submit",
        "https://outside.invalid/",
        "file:///tmp/private",
        "data:image/png;base64,eA==",
    ]:
        page.callback(
            SimpleNamespace(
                request=SimpleNamespace(url=url),
                continue_=lambda: actions.append("allow"),
                abort=lambda: actions.append("block"),
            )
        )
    assert actions == ["allow", "block", "block", "block", "allow"]


ILLEGAL_INPUTS: list[tuple[str, object]] = [
    ("endpoint", None),
    ("endpoint", ""),
    ("endpoint", 7),
    ("endpoint", []),
    ("endpoint", "http://remote:18080/"),
    ("endpoint", "http://127.0.0.1/"),
    ("endpoint", "https://127.0.0.1:18080/"),
    ("endpoint", "http://127.0.0.1:1023/"),
    ("endpoint", "http://127.0.0.1:65536/"),
    ("endpoint", "http://user@127.0.0.1:18080/"),
    ("endpoint", "http://127.0.0.1:18080/submit"),
    ("endpoint", "http://127.0.0.1:18080/?q=1"),
    (
        "endpoint",
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    ),
    ("native_account_id", None),
    ("native_account_id", True),
    ("native_account_id", "17"),
    ("native_account_id", 0),
    ("native_account_id", -1),
    ("native_account_id", []),
    ("native_account_id", 9223372036854775808),
    (
        "native_account_id",
        1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000,
    ),
    ("native_account_username", None),
    ("native_account_username", True),
    ("native_account_username", 17),
    ("native_account_username", ""),
    ("native_account_username", "a/b"),
    ("native_account_username", "a b"),
    ("native_account_username", "a\n"),
    (
        "native_account_username",
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    ),
]


@pytest.mark.parametrize("field,value", ILLEGAL_INPUTS)
def test_illegal_private_inputs_rejected(field: str, value: Any) -> None:
    data = selection().model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValueError):
        RedditNativeImageInitialization.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("port", [1024, 65535])
def test_original_endpoint_boundaries(port: int) -> None:
    data = selection().model_dump(mode="json")
    data["endpoint"] = f"http://127.0.0.1:{port}/"
    selected = RedditNativeImageInitialization.model_validate_json(json.dumps(data))
    selected.check_task(
        task().model_copy(update={"start_url": selected.endpoint + "submit"})
    )


@pytest.mark.parametrize("field", ["prepared_ref", "site_ref"])
@pytest.mark.parametrize(
    "change",
    [
        {"visibility": "public"},
        {"media_type": "text/plain"},
        {"content_schema": "wrong/1"},
    ],
)
def test_wrong_original_private_reference_rejected(
    field: str, change: dict[str, str]
) -> None:
    data = selection().model_dump(mode="json")
    data[field].update(change)
    with pytest.raises(ValueError):
        RedditNativeImageInitialization.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("kind", ["family", "split", "route", "scope", "port"])
def test_wrong_task_or_attempt_refused_before_credential_read(kind: str) -> None:
    selected = selection()
    public = task()
    spec = frozen(public.start_url)
    if kind in ("family", "split"):
        public = public.model_copy(
            update={
                "identity": public.identity.model_copy(
                    update={kind: "wrong" if kind == "family" else "test"}
                )
            }
        )
    elif kind == "route":
        public = public.model_copy(
            update={"start_url": selected.endpoint + "f/EarthPorn"}
        )
    elif kind == "port":
        public = public.model_copy(
            update={"start_url": "http://127.0.0.1:18081/submit"}
        )
    else:
        spec = spec.model_copy(
            update={"scope": spec.scope.model_copy(update={"context_id": "other"})}
        )
    setup = RedditNativeImageBrowserInitializer(
        selected, lambda c: pytest.fail("Wrong task cannot read credentials")
    )
    with pytest.raises(ValueError):
        if kind == "scope":
            selected.check(spec)
        else:
            setup.setup(Page(), public, guard(5))


@pytest.mark.parametrize(
    "event", ["goto", "form_ready", "fill", "click", "account_ready", "account_name"]
)
def test_original_login_failure_closes_and_cannot_retry(event: str) -> None:
    page = Page()
    page.login.failure = event
    setup = RedditNativeImageBrowserInitializer(
        selection(), lambda c: ("native-user", "private-password")
    )
    with pytest.raises(RuntimeError, match="fault-"):
        setup.setup(page, task(), guard(5))
    assert page.login.calls[-1] == "close"
    assert page.calls == ["route", "new_page"]
    with pytest.raises(RuntimeError, match="already attempted"):
        setup.setup(page, task(), guard(5))


@pytest.mark.parametrize(
    "kind", ["login-name", "dom-name", "logged-out", "http503", "close-and-primary"]
)
def test_account_health_and_dual_failure_are_not_hidden(kind: str) -> None:
    page = Page()
    credentials = ("native-user", "private-password")
    if kind == "login-name":
        credentials = ("different-user", "private-password")
    elif kind == "dom-name":
        page.login.account = "different-user"
    elif kind == "logged-out":
        page.login.logged_out = True
    elif kind == "http503":
        page.login.status = 503
    else:
        page.login.failure = "click"
        page.login.close_error = True
    setup = RedditNativeImageBrowserInitializer(selection(), lambda c: credentials)
    with pytest.raises(
        BaseExceptionGroup if kind == "close-and-primary" else RuntimeError
    ) as caught:
        setup.setup(page, task(), guard(5))
    assert "private-password" not in str(caught.value)
    if kind == "login-name":
        assert page.calls == []
    else:
        assert page.login.calls[-1] == "close"


def test_native_prepared_binding_requires_reddit_checks_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prepared_browser_fixtures import prepared_case
    from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
    from lab_generate_skill.domain.errors import OwnershipConflict

    with prepared_case(tmp_path, monkeypatch) as c:
        config = c.browser.spec.configuration
        public = task()
        session = config.spec.model_copy(
            update={
                "task": public,
                "scope": config.spec.scope.model_copy(update={"task": public.identity}),
            }
        )
        selected = selection().model_copy(
            update={
                "task_files": reddit_photo_plan(
                    session.scope, "/tmp/engineering-reddit/browser-uploads"
                )
            }
        )
        data = config.model_dump(mode="json")
        data.update(
            spec=session.model_dump(mode="json"),
            initialization=selected.model_dump(mode="json"),
        )
        changed = BrowserWorkerConfiguration.model_validate_json(json.dumps(data))
        resource = c.browser.spec.model_copy(update={"configuration": changed})
        with pytest.raises(OwnershipConflict, match="requires fixed task checks"):
            c.binding.verify(resource, c.browser.op, guard())
        assert not c.browser.channels
