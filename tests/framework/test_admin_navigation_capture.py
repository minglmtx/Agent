"""New collector and common-engine seam only; unchanged binding proof reused.

Chromium reads local synthetic pages, never an Admin deployment or task source.
Only the original asset path is reused; no old owner/receipt grants permission.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from types import SimpleNamespace
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminNavigationPage
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.navigation_page_capture import (
    AdminNavigationPageCollector,
)
from lab_generate_skill.evaluators.shopping_admin.navigation_predicates import (
    navigation_checks,
)
from test_admin_navigation_input import (
    contracts as contracts,
    original_checks as original_checks,
)
from browser_worker_fixtures import case
from browsergym_fixtures import operation, LoopbackAuthority
from test_slurm_commands import guard

ROOT = Path("/anvme/workspace/r102bf10-lab-generate-skill")


def test_actual_chromium_fixed_capture_and_binding_predicates(
    contracts: Any, original_checks: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes: dict[str, str] = {}
    for native, _, _ in contracts:
        target = "/admin" + native["spec"]["target_path"].rstrip("/")
        heading = native["spec"]["heading"]
        assert target not in routes or routes[target] == heading
        routes[target] = heading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            heading = routes.get(self.path, "Wrong heading")
            body = (
                "<!doctype html><title>Software fixture</title><main><h1>"
                + html.escape(heading)
                + "</h1></main>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html;charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    netloc = "127.0.0.1:" + str(server.server_port)
    receipt = json.loads(
        (
            ROOT
            / "experiments/framework-map-navigation42-production-20261102-v1/source-qualification-4888671/source-only-qualification.json"
        ).read_text()
    )
    facts = json.loads(Path(receipt["facts_path"]).read_text())
    configuration = facts["prepared_browser"]["browser_spec"]["configuration"]
    chromium = configuration["spec"]["chromium_executable"]
    libraries = configuration["library_directories"]
    assert libraries and all(
        Path(x).is_dir() and Path(x).resolve().is_relative_to(ROOT) for x in libraries
    )
    monkeypatch.setenv("LD_LIBRARY_PATH", ":".join(libraries))
    collector = AdminNavigationPageCollector()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chromium,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = browser.new_page()
                for native, reference, public in contracts:
                    spec = bind_admin_navigation(native, reference, public).private_spec
                    page.goto(
                        "http://"
                        + netloc
                        + "/admin"
                        + native["spec"]["target_path"].rstrip("/"),
                        wait_until="domcontentloaded",
                        timeout=10000,
                    )
                    captured = AdminNavigationPage.model_validate_json(
                        collector.collect(page, "admin-navigation-page", "1", guard())
                    )
                    assert captured.heading == spec.heading
                    assert captured.url == page.url
                    checks = navigation_checks(spec, captured, netloc)
                    assert checks == original_checks(
                        native["spec"], captured.model_dump(), netloc
                    )
                    assert all(checks.values())
                page.set_content(
                    '<main><h1>Dashboard</h1><form id="login-form"><input type="password"></form></main>'
                )
                captured = AdminNavigationPage.model_validate_json(
                    collector.collect(page, "admin-navigation-page", "1", guard())
                )
                assert captured.login and not captured.page_error
                page.set_content("<main>Whoops, our bad<h1>Dashboard</h1></main>")
                captured = AdminNavigationPage.model_validate_json(
                    collector.collect(page, "admin-navigation-page", "1", guard())
                )
                assert captured.page_error and not captured.login
                page.set_content("<main>No heading</main>")
                captured = AdminNavigationPage.model_validate_json(
                    collector.collect(page, "admin-navigation-page", "1", guard())
                )
                assert captured.heading == ""
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "terminal",
        "collector",
        "version",
        "native",
        "bad_bool",
        "missing_heading",
        "cancel_before_read",
        "cancel_after_read",
    ],
)
def test_common_engine_capture_once_and_retains_measured_fact(fault: str) -> None:
    _, _, _, client = case()
    initial = client.start(operation(client.spec, "start"), control=guard())
    calls: list[str] = []

    class Control:
        def checkpoint(self) -> float:
            if fault == "cancel_before_read" or (
                fault == "cancel_after_read" and calls
            ):
                raise OperationStopped("CANCELLED", "capture")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    class Page:
        def evaluate(self, script: str) -> dict[str, Any]:
            calls.append(script)
            if fault == "native":
                raise OSError("original page unavailable")
            raw = {
                "schema_version": "admin-navigation-page/1",
                "url": client.spec.task.start_url,
                "heading": "Dashboard",
                "login": "false" if fault == "bad_bool" else False,
                "page_error": False,
            }
            if fault == "missing_heading":
                del raw["heading"]
            return raw

    engine = BrowserGymEngine(
        client.spec,
        LoopbackAuthority(),
        SystemClock(),
        NavigatePublicTask(),
        collector=AdminNavigationPageCollector(),
    )
    engine.state = "terminal" if fault == "terminal" else "ready"
    engine.last_readout = initial
    engine.env = SimpleNamespace(page=Page())
    request = BrowserCaptureRequest(
        scope=client.spec.scope,
        operation=operation(client.spec, "capture"),
        observation_sha256=hashlib.sha256(
            initial.observation.model_dump_json().encode()
        ).hexdigest(),
        collector_id="wrong" if fault == "collector" else "admin-navigation-page",
        collector_version="2" if fault == "version" else "1",
    )
    if fault in ("none", "terminal"):
        result = engine.capture_page(request, control=Control())
        assert result.request_sha256 == request.digest
        assert (
            AdminNavigationPage.model_validate_json(result.private_result).heading
            == "Dashboard"
        )
        assert len(calls) == 1
        with pytest.raises(InvalidTransition):
            engine.capture_page(request, control=Control())
        assert len(calls) == 1
    else:
        with pytest.raises((ValueError, OSError, OperationStopped)):
            engine.capture_page(request, control=Control())
        assert len(calls) == (
            0 if fault in ("collector", "version", "cancel_before_read") else 1
        )
        if fault == "cancel_after_read":
            assert engine.last_capture is not None
            assert engine.last_capture.request_sha256 == request.digest
            assert (
                AdminNavigationPage.model_validate_json(
                    engine.last_capture.private_result
                ).heading
                == "Dashboard"
            )
