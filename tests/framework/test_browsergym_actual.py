"""Real Chromium on a loopback form, with original evidence/closure boundaries.

No production website, paid request or training source is touched. BrowserGym
runs in this Slurm test worker; production external supervision is still pending.
"""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.browser import BrowserActions
from evidence_control_fixtures import EvidenceFixtureStore
from test_slurm_commands import guard
from browsergym_fixtures import spec, operation, LoopbackAuthority, CHROMIUM


def test_actual_navigation_capture_save_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    posts: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b'<html><title>Product</title><form method="post"><label for="description">Description</label><textarea id="description" name="description">Original</textarea><button type="submit">Save</button></form></html>'
            )

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            value = parse_qs(body.decode())["description"][0]
            posts.append(value)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                ("<html><title>Saved</title><p>" + value + "</p></html>").encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    frozen = spec(f"http://127.0.0.1:{server.server_port}/")
    engine = BrowserGymEngine(
        frozen, LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    store = EvidenceFixtureStore(tmp_path)
    session = EvidenceBrowserSession(engine, store)
    browser: BrowserActions = session
    original = operation(frozen, "initial")
    primary: BaseException | None = None
    try:
        initial_ref = session.start(original, control=guard(90))
        initial = engine.last_readout
        assert initial is not None and initial.observation.sequence == 0
        assert initial.events[0].kind == "before_navigation"
        assert any(
            e.kind == "response" and e.url == frozen.task.start_url and e.status == 200
            for e in initial.events
        )
        text = initial.observation.text or ""
        match = re.search(r"\[([^\]]+)\] textbox [\'\"]Description[\'\"]", text)
        button = re.search(r"\[([^\]]+)\] button [\'\"]Save[\'\"]", text)
        assert match and button, text
        fill = BrowserAction(
            action_id="fill-description",
            protocol_id="browsergym-highlevel-v1",
            name="fill",
            payload=f"fill({match.group(1)!r}, 'Updated description')",
        )
        filled = browser.step(fill, operation(frozen, "fill"), control=guard(60))
        assert filled.before_observation_ref == initial_ref
        save = BrowserAction(
            action_id="save-description",
            protocol_id="browsergym-highlevel-v1",
            name="click",
            payload=f"click({button.group(1)!r})",
        )
        result = browser.step(save, operation(frozen, "save"), control=guard(60))
        assert (
            posts == ["Updated description"]
            and result.before_observation_ref == filled.observation_ref
        )
        raw = BrowserReadout.model_validate_json(store.read(result.return_ref))
        assert raw.schema_version == result.return_ref.content_schema
        assert raw.action == save and raw.operation == result.operation
        assert (
            "Updated description" in (raw.observation.text or "")
            and not raw.observation.last_action_error
        )
        assert [e.action_id for e in raw.events if e.kind == "before_action"] == [
            fill.action_id,
            save.action_id,
        ]
        assert [e.action_id for e in raw.events if e.kind == "after_action"] == [
            fill.action_id,
            save.action_id,
        ]
        with pytest.raises(InvalidTransition):
            browser.step(save, operation(frozen, "save"), control=guard(10))
        assert posts == ["Updated description"]
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output:
            (Path(output) / "browsergym-loopback.json").write_text(
                json.dumps(
                    {
                        "initial": initial_ref.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                        "readout": raw.model_dump(mode="json"),
                        "posts": posts,
                        "production_site": False,
                    },
                    indent=2,
                )
                + "\n"
            )
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup = original.cleanup(
            "close-browser", now=datetime.now(timezone.utc), seconds=30
        )
        try:
            session.close(cleanup, control=guard(30))
            assert engine.state == "closed" and engine.driver is None
            session.close(cleanup, control=guard(30))
        except BaseException as error:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Test and browser cleanup failures", [primary, error]
                )
            raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
