"""Controlled duplicate DOM and delayed native form readiness; no DB or Actor."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs
import pytest
from lab_generate_skill.domain.browser_initialization import ShoppingOrderInitialization
from lab_generate_skill.sites.shopping.browser_initialization import (
    ShoppingOrderBrowserInitializer,
)
from browsergym_fixtures import CHROMIUM
from browser_worker_fixtures import LIBS
from test_core_contracts import reference
from test_shopping_order_eta_inputs import public_task
from test_slurm_commands import guard


def test_real_scoped_login_ignores_popup_and_waits_for_original_form_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert os.environ.get("SLURM_JOB_ID")
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
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = (
                '<form id="login-form" method="post" action="/customer/account/loginPost/"><input name="form_key" value="">'
                '<input id="email" name="login[username]"><input id="pass" name="login[password]" type="password">'
                '<button id="send2" type="submit">Sign In</button></form>'
                '<div hidden><form id="login-form"><input id="customer-email" name="username"><input id="pass" name="password"><button id="send2" type="submit">Sign In</button></form></div>'
                '<script>setTimeout(()=>{document.cookie="form_key=controlled-token; path=/";'
                'document.querySelector("form#login-form[action] input[name=form_key]").value="controlled-token";},150);</script>'
                if self.path.startswith("/customer/account/login")
                else '<body class="customer-account-index"><div class="block-dashboard-info"><div class="box-information">private-user@example.test</div></div></body>'
            )
            self.wfile.write(
                ("<html><title>Controlled account</title>" + body + "</html>").encode()
            )

        def do_POST(self) -> None:
            values = parse_qs(
                self.rfile.read(int(self.headers["Content-Length"])).decode()
            )
            posts.append(values)
            assert values == {
                "form_key": ["controlled-token"],
                "login[username]": ["private-user@example.test"],
                "login[password]": ["controlled-password"],
            }
            assert "form_key=controlled-token" in self.headers.get("Cookie", "")
            self.send_response(303)
            self.send_header("Location", "/customer/account/")
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
                config = ShoppingOrderInitialization(
                    endpoint=endpoint,
                    prepared_ref=reference(content_schema="prepared-task/1"),
                    site_ref=reference(content_schema="site-resource-started/1"),
                )
                initializer = ShoppingOrderBrowserInitializer(
                    config,
                    lambda control: (
                        "private-user@example.test",
                        "controlled-password",
                    ),
                )
                initializer.setup(
                    page,
                    public_task(start_url=endpoint + "customer/account/"),
                    guard(15),
                )
                assert len(posts) == 1 and len(page.context.pages) == 1
                assert page.url == endpoint + "customer/account/"
                with pytest.raises(RuntimeError, match="already attempted"):
                    initializer.setup(page, public_task(start_url=page.url), guard(5))
                assert len(posts) == 1
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "shopping-login-controlled.json"
    ).write_text(
        json.dumps(
            {
                "engineering_only": True,
                "real_chromium": True,
                "duplicate_ids": True,
                "form_cookie_ready_before_submit": True,
                "original_posts": len(posts),
                "website_started": False,
                "actor_calls": 0,
                "paid_calls": 0,
            },
            indent=2,
        )
        + "\n"
    )
