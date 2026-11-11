"""Actual Chromium main-document status/DOM; controlled HTTP only, no DB/Actor."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import pytest
from lab_generate_skill.sites.shopping.page_capture import (
    ShoppingPageHealthCollector,
    ShoppingPageHealth,
)
from browsergym_fixtures import CHROMIUM
from test_slurm_commands import guard


def test_actual_native_main_document_status_not_subresource_or_guessed_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert os.environ.get("SLURM_JOB_ID")
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )

    class Handler(BaseHTTPRequestHandler):
        requests = 0
        same_url_error = False

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            Handler.requests += 1
            status = (
                503
                if self.path.startswith("/server-error") or Handler.same_url_error
                else 404 if self.path.startswith("/missing") else 200
            )
            title = "Whoops, our bad..." if status == 404 else "Account Dashboard"
            login = self.path.startswith("/customer/account/login")
            body = (
                '<form class="form-login"><input type="password"></form>'
                if login
                else "<main>Account ready</main>"
            )
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                ("<html><title>" + title + "</title>" + body + "</html>").encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    facts = []
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(executable_path=CHROMIUM, headless=True)
            try:
                page = browser.new_page()
                collector = ShoppingPageHealthCollector()
                for path, status, login, error in [
                    ("/account", 200, False, False),
                    ("/customer/account/login/", 200, True, False),
                    ("/missing", 404, False, True),
                    ("/server-error", 503, False, True),
                ]:
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}" + path,
                        wait_until="networkidle",
                    )
                    before = Handler.requests
                    captured = ShoppingPageHealth.model_validate_json(
                        collector.collect(page, "shopping-page-health", "1", guard(10))
                    )
                    assert (
                        captured.http_status,
                        captured.login_page,
                        captured.error_page,
                    ) == (status, login, error)
                    assert (
                        Handler.requests == before
                        and captured.status_source == "navigation_timing"
                    )
                    facts.append(captured.model_dump(mode="json"))
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/account",
                    wait_until="networkidle",
                )
                Handler.same_url_error = True
                page.evaluate("async () => { await fetch(location.href); }")
                before = Handler.requests
                captured = ShoppingPageHealth.model_validate_json(
                    collector.collect(page, "shopping-page-health", "1", guard(10))
                )
                assert (
                    captured.http_status == 200
                    and not captured.error_page
                    and Handler.requests == before
                )
                facts.append(captured.model_dump(mode="json"))
                blank = browser.new_page()
                blank.set_content("<title>No HTTP document</title><main>Blank</main>")
                captured = ShoppingPageHealth.model_validate_json(
                    collector.collect(blank, "shopping-page-health", "1", guard(10))
                )
                assert (
                    captured.http_status is None
                    and captured.status_source == "unavailable"
                )
                facts.append(captured.model_dump(mode="json"))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "shopping-main-document.json"
    )
    with output.open("x") as stream:
        json.dump(
            {
                "engineering_only": True,
                "website_started": False,
                "actor_calls": 0,
                "paid_calls": 0,
                "captures": facts,
            },
            stream,
            indent=2,
        )
