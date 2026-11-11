"""Controlled native Chromium login and unchanged public submit initialization."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.browser_task_files import browser_task_files
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.sites.reddit.browser_initialization import (
    RedditNativeImageBrowserInitializer,
)
from browsergym_fixtures import CHROMIUM, LoopbackAuthority, operation
from browser_worker_fixtures import configuration
from test_browser_task_files_actual import frozen
from test_slurm_commands import guard
from test_core_contracts import reference
from reddit_login_http_fixture import RedditLoginFixture


def test_new_http_fixture_checks_original_csrf_fields_and_has_no_post_shortcut() -> (
    None
):
    with RedditLoginFixture() as fixture:
        with urllib.request.urlopen(fixture.endpoint + "login", timeout=5) as response:
            assert response.status == 200 and b'name="_csrf_token"' in response.read()
        data = urllib.parse.urlencode(
            {"_username": "native-user", "_password": "engineering-private-password"}
        ).encode()
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(
                fixture.endpoint + "login_check", data=data, timeout=5
            )
        assert caught.value.code == 403
        caught.value.close()
        assert fixture.posts == ["/login_check"]


@pytest.mark.parametrize("wrong_account", [False, True])
def test_actual_native_login_retains_public_submit_and_refuses_wrong_account(
    monkeypatch: pytest.MonkeyPatch, wrong_account: bool
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    old = Path.cwd()
    with (
        RedditLoginFixture(wrong_account=wrong_account) as fixture,
        tempfile.TemporaryDirectory(
            prefix="lab-reddit-login-", dir="/tmp"
        ) as directory,
    ):
        session = frozen(fixture.endpoint + "submit")
        selected = RedditNativeImageInitialization(
            endpoint=fixture.endpoint,
            native_account_id=17,
            native_account_username="native-user",
            prepared_ref=reference(content_schema="prepared-task/1"),
            site_ref=reference(content_schema="site-resource-started/1"),
            task_files=reddit_photo_plan(
                session.scope, str(Path(directory) / "browser-uploads")
            ),
        )
        base = configuration().model_dump(mode="json")
        base.update(
            spec=session.model_dump(mode="json"),
            initialization=selected.model_dump(mode="json"),
        )
        config = BrowserWorkerConfiguration.model_validate_json(json.dumps(base))
        initializer = RedditNativeImageBrowserInitializer(
            selected, lambda c: ("native-user", "engineering-private-password")
        )
        engine = BrowserGymEngine(
            session,
            LoopbackAuthority(),
            SystemClock(),
            initializer,
            task_files=browser_task_files(config),
        )
        primary: BaseException | None = None
        try:
            if wrong_account:
                with pytest.raises(RuntimeError, match="original native account"):
                    engine.start(operation(session, "initial"), control=guard(90))
                assert (
                    engine.last_readout is None and str(engine.state) == "quarantined"
                )
                assert "/submit" not in fixture.gets
            else:
                readout = engine.start(operation(session, "initial"), control=guard(90))
                assert (
                    readout.observation.sequence == 0
                    and readout.observation.state == "ready"
                )
                assert not readout.observation.last_action_error
                assert all(
                    "engineering-private-password" not in str(v)
                    for v in [readout.observation.text, readout.model_dump_json()]
                )
                assert engine.env.page.url == session.task.start_url
                assert (
                    engine.env.page.locator('[name="submission[image]"]').evaluate(
                        "e=>e.files.length"
                    )
                    == 0
                )
                assert (
                    engine.env.page.locator('[name="submission[title]"]').input_value()
                    == ""
                )
                assert (
                    engine.env.page.locator('[name="submission[forum]"]').input_value()
                    == ""
                )
                assert len(engine.env.page.context.pages) == 1
            assert fixture.posts == ["/login_check"]  # initialization creates no post
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                engine.close(
                    operation(session, "cleanup-parent").cleanup(
                        "close", now=datetime.now(timezone.utc), seconds=30
                    ),
                    control=guard(30),
                )
            except BaseException as cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Login and cleanup failed", [primary, cleanup]
                    ) from None
                raise
        assert str(engine.state) == "closed" and Path.cwd() == old
    assert not Path(directory).exists()
