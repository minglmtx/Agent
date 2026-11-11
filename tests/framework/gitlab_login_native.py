"""Controlled real Chromium login; fixed-image selectors, no GitLab DB/Actor."""

from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs
import pytest
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from lab_generate_skill.sites.gitlab.browser_initialization import (
    GitlabSshKeyBrowserInitializer,
)
from browsergym_fixtures import CHROMIUM
from browser_worker_fixtures import LIBS
from test_core_contracts import reference
from test_gitlab_ssh_key_inputs import public_task
from test_slurm_commands import guard
from lab_generate_skill.sites.gitlab.page_capture import (
    GitlabPageHealthCollector,
    GitlabPageHealth,
)

LOGIN = """<html><title>Controlled native login</title>
<form id="new_user" data-testid="sign-in-form" method="post" action="/users/sign_in">
<input name="authenticity_token" value="">
<input id="user_login" name="user[login]" required>
<input id="user_password" name="user[password]" type="password" required>
<button type="submit" data-testid="sign-in-button">Sign in</button></form>
<div hidden><form id="popup"><input id="user_login" name="username"><input id="user_password" type="password"><button>Sign in</button></form></div>
<script>setTimeout(()=>{document.querySelector('form[data-testid="sign-in-form"] input[name="authenticity_token"]').value='controlled-csrf';},120);</script>
</html>"""


def test_controlled_fixture_has_native_post_contract_and_separate_popup() -> None:
    class Forms(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.forms: list[dict[str, str | None]] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag == "form":
                self.forms.append(dict(attrs))

    parser = Forms()
    parser.feed(LOGIN)
    assert len(parser.forms) == 2
    main, popup = parser.forms
    assert main["method"] == "post" and main["action"] == "/users/sign_in"
    assert main["data-testid"] == "sign-in-form" and "data-testid" not in popup


@pytest.mark.parametrize("wrong_account", [False, True])
def test_real_scoped_gitlab_login_retains_root_and_rejects_foreign_account(
    monkeypatch: pytest.MonkeyPatch,
    wrong_account: bool,
) -> None:
    assert os.environ["SLURM_JOB_ID"]
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH", LIBS + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    )
    posts: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/unrelated-xhr":
                self.send_response(500)
                self.end_headers()
                return
            if (
                self.path != "/users/sign_in"
                and "controlled_auth=1" not in self.headers.get("Cookie", "")
            ):
                self.send_response(303)
                self.send_header("Location", "/users/sign_in")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            account_id = 18 if wrong_account else 17
            body = (
                LOGIN
                if self.path == "/users/sign_in"
                else "<html><title>Projects</title><script>window.gon={current_user_id:"
                + str(account_id)
                + "};</script><h1>Your projects</h1></html>"
            )
            self.wfile.write(body.encode())

        def do_POST(self) -> None:
            values = parse_qs(
                self.rfile.read(int(self.headers["Content-Length"])).decode()
            )
            posts.append(values)
            assert self.path == "/users/sign_in"
            assert values == {
                "authenticity_token": ["controlled-csrf"],
                "user[login]": ["native-user"],
                "user[password]": ["controlled-password"],
            }
            self.send_response(303)
            self.send_header("Set-Cookie", "controlled_auth=1; Path=/; HttpOnly")
            self.send_header("Location", "/")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(executable_path=CHROMIUM, headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                endpoint = f"http://127.0.0.1:{server.server_port}/"
                selected = GitlabSshKeyInitialization(
                    endpoint=endpoint,
                    native_account_id=17,
                    prepared_ref=reference(content_schema="prepared-task/1"),
                    site_ref=reference(content_schema="site-resource-started/1"),
                )
                initializer = GitlabSshKeyBrowserInitializer(
                    selected, lambda control: ("native-user", "controlled-password")
                )
                task = public_task(start_url=endpoint)
                if wrong_account:
                    with pytest.raises(RuntimeError, match="original native account"):
                        initializer.setup(page, task, guard(15))
                else:
                    initializer.setup(page, task, guard(15))
                    assert page.url == endpoint
                    assert (
                        page.evaluate("() => fetch('/unrelated-xhr').then(r=>r.status)")
                        == 500
                    )
                    fact = GitlabPageHealth.model_validate_json(
                        GitlabPageHealthCollector().collect(
                            page, "gitlab-page-health", "1", guard(5)
                        )
                    )
                    assert fact.url == endpoint and fact.account_id == 17
                    assert (
                        fact.http_status == 200
                        and fact.status_source == "navigation_timing"
                    )
                    assert not fact.error_page and not fact.login_page
                assert len(posts) == 1 and len(context.pages) == 1
                with pytest.raises(RuntimeError, match="already attempted"):
                    initializer.setup(page, task, guard(5))
                assert len(posts) == 1
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
        "gitlab-login-controlled-" + str(wrong_account).lower() + ".json"
    )
    output.write_text(
        json.dumps(
            dict(
                engineering_only=True,
                real_chromium=True,
                wrong_account_rejected=wrong_account,
                retained_public_root=not wrong_account,
                duplicate_popup_ignored=True,
                csrf_ready_before_submit=True,
                original_posts=len(posts),
                website_started=False,
                actor_calls=0,
                paid_calls=0,
            ),
            indent=2,
        )
        + "\n"
    )
