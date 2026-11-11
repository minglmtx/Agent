"""Controlled HTTP documents in pinned Chromium; no Postmill/model/db effects."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading
import pytest
from lab_generate_skill.sites.reddit.page_capture import RedditPageHealthCollector
from lab_generate_skill.sites.reddit.evidence_schema import RedditPageHealth
from browsergym_fixtures import CHROMIUM
from test_slurm_commands import guard


def document(path: str) -> tuple[int, bytes]:
    status = 404 if path == "/404" else 503 if path == "/503" else 200
    form = (
        '<form action="/login_check"><input type="password"></form>'
        if path == "/form"
        else "<main>Native page</main>"
    )
    return (
        status,
        (
            '<html><head><link rel="icon" href="data:,"><title>Controlled Reddit</title></head><body>'
            + form
            + "</body></html>"
        ).encode(),
    )


def test_fixture_document_cases_are_explicit_before_native_run() -> None:
    assert [
        document(path)[0] for path in ("/submit", "/login", "/form", "/404", "/503")
    ] == [200, 200, 200, 404, 503]
    assert b"/login_check" in document("/form")[1]
    assert all(
        b"/login_check" not in document(path)[1]
        for path in ("/submit", "/login", "/404", "/503")
    )


def test_original_main_document_status_and_login_in_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            calls.append(self.path)
            status, body = document(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(executable_path=CHROMIUM, headless=True)
            try:
                page = browser.new_page()
                collector = RedditPageHealthCollector()
                for path, expected, login in (
                    ("/submit", 200, False),
                    ("/login", 200, True),
                    ("/form", 200, True),
                    ("/404", 404, False),
                    ("/503", 503, False),
                ):
                    page.goto(origin + path, wait_until="networkidle")
                    before = tuple(calls)
                    for _ in range(2):
                        actual = RedditPageHealth.model_validate_json(
                            collector.collect(
                                page, "reddit-page-health", "1", guard(10)
                            )
                        )
                        assert (
                            actual.http_status,
                            actual.login_page,
                            actual.error_page,
                        ) == (expected, login, expected >= 400)
                        assert (
                            actual.status_source == "navigation_timing"
                            and actual.url == page.url
                        )
                    assert tuple(calls) == before
                page.goto(origin + "/submit", wait_until="networkidle")
                page.evaluate("async()=>{await fetch('/503');}")
                actual = RedditPageHealth.model_validate_json(
                    collector.collect(page, "reddit-page-health", "1", guard(10))
                )
                assert actual.http_status == 200 and not actual.error_page
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()
