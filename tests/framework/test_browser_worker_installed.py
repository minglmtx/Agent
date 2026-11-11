"""Actual fixed installed BrowserGym child on loopback, no production permission.

Each case owns its server/process session; installed preparation is reused. The
native deadline case proves the original channel/worker stops, not escaped
browser descendants or restoration of a production website.
"""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import threading
import time
import pytest
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
    fixed_browser_argv,
)
from lab_generate_skill.adapters.browsergym.worker_protocol import MAX_PACKET
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.ports.browser_session import RawBrowserSession
from lab_generate_skill.ports.lifecycle import OperationControl
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from browser_worker_fixtures import configuration
from browsergym_fixtures import operation, LoopbackAuthority
from evidence_control_fixtures import EvidenceFixtureStore
from test_slurm_commands import guard


@pytest.mark.parametrize("behavior", ["normal", "native_deadline"])
def test_installed_actual_browser_session(
    installed_sources: InstalledFixture, tmp_path: Path, behavior: str
) -> None:
    entered = threading.Event()

    class EnteredDeadline:
        def __init__(self) -> None:
            self.overall = guard(15)
            self.after_entry: OperationControl | None = None

        def checkpoint(self) -> float:
            remaining = self.overall.checkpoint()
            if entered.is_set() and self.after_entry is None:
                self.after_entry = guard(0.2)
            return (
                min(remaining, self.after_entry.checkpoint())
                if self.after_entry is not None
                else remaining
            )

        def wait(self, seconds: float) -> None:
            time.sleep(min(seconds, self.checkpoint(), 0.02))
            self.checkpoint()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/blocked":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"entered")
                entered.set()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Product</title><label for='description'>Description</label><input id='description'><button onclick=\"document.title=document.getElementById('description').value\">Save</button><button onclick=\"var r=new XMLHttpRequest();r.open('GET','/blocked',false);r.send();while(true){}\">Block</button></html>"
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = configuration(
        storage_installation(installed_sources),
        f"http://127.0.0.1:{server.server_port}/",
    )
    channel = FramedProcessSession(
        fixed_browser_argv(config), max_frame_bytes=MAX_PACKET
    )
    client = SupervisedBrowserSession(
        channel, "installed-browser", config, LoopbackAuthority()
    )
    capability: RawBrowserSession = client
    store = EvidenceFixtureStore(tmp_path)
    session = EvidenceBrowserSession(capability, store)
    op = operation(config.spec, "initial")
    primary: BaseException | None = None
    observed_worker = None
    try:
        channel.start(guard(30))
        initial_ref = session.start(op, control=guard(90))
        assert (
            client.configuration_reply is not None
            and client.configuration_reply.owner_guard is not None
        )
        ownership = client.configuration_reply.owner_guard
        observed_worker = ownership.worker
        assert (
            ownership.controller == client.controller
            and ownership.supervisor.process_id == channel.process_id
        )
        assert client.configuration_reply.installed_sources is not None
        assert client.last_readout is not None
        text = client.last_readout.observation.text or ""
        assert client.last_readout.events[0].kind == "before_navigation"
        assert any(
            e.kind == "response" and e.status == 200 for e in client.last_readout.events
        )
        if behavior == "normal":
            textbox = re.search(r"\[([^\]]+)\] textbox ['\"]Description['\"]", text)
            save = re.search(r"\[([^\]]+)\] button ['\"]Save['\"]", text)
            assert textbox and save, text
            filled = session.step(
                BrowserAction(
                    action_id="fill",
                    protocol_id="browsergym-highlevel-v1",
                    name="fill",
                    payload=f"fill({textbox.group(1)!r}, 'Updated')",
                ),
                operation(config.spec, "fill"),
                control=guard(30),
            )
            assert filled.before_observation_ref == initial_ref
            result = session.step(
                BrowserAction(
                    action_id="save",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({save.group(1)!r})",
                ),
                operation(config.spec, "save"),
                control=guard(30),
            )
            returned = BrowserReadout.model_validate_json(store.read(result.return_ref))
            assert (
                returned.observation.tabs[0].title == "Updated"
                and returned.action is not None
                and returned.action.action_id == "save"
            )
            assert result.before_observation_ref == filled.observation_ref
            assert client.sequence == 4 and observed_worker == ownership.worker
        else:
            block = re.search(r"\[([^\]]+)\] button ['\"]Block['\"]", text)
            assert block, text
            started = time.monotonic()
            with pytest.raises(OperationStopped):
                session.step(
                    BrowserAction(
                        action_id="block",
                        protocol_id="browsergym-highlevel-v1",
                        name="click",
                        payload=f"click({block.group(1)!r})",
                    ),
                    operation(config.spec, "block"),
                    control=EnteredDeadline(),
                )
            assert (
                entered.is_set()
            ), "Deadline expired before browser entered the marked native path"
            assert time.monotonic() - started < 8 and client.state == "quarantined"
            assert (
                channel.capture.termination is not None
                and channel.capture.termination.state == "reaped"
            )
            until = time.monotonic() + 5
            proc = Path(f"/proc/{observed_worker.process_id}/stat")
            while proc.exists() and time.monotonic() < until:
                try:
                    state = proc.read_text().rsplit(")", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                time.sleep(0.02)
            else:
                if proc.exists():
                    raise AssertionError(
                        "Original browser worker still live after abort"
                    )
            with pytest.raises(InvalidTransition):
                session.step(
                    BrowserAction(
                        action_id="again",
                        protocol_id="browsergym-highlevel-v1",
                        name="click",
                        payload=f"click({block.group(1)!r})",
                    ),
                    operation(config.spec, "again"),
                    control=guard(1),
                )
            assert client.sequence == 3
        cleanup = op.cleanup("close", now=datetime.now(timezone.utc), seconds=30)
        session.close(cleanup, control=guard(30))
        session.close(cleanup, control=guard(30))
        assert client.state == "closed" and channel.capture.termination is not None
        assert channel.capture.termination.state == "reaped"
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output:
            (Path(output) / f"browser-worker-{behavior}.json").write_text(
                json.dumps(
                    {
                        "configuration": config.model_dump(mode="json"),
                        "original_guard": ownership.model_dump(mode="json"),
                        "last_reply": (
                            client.last_reply.model_dump(mode="json")
                            if client.last_reply
                            else None
                        ),
                        "sequence": client.sequence,
                        "returncode": channel.capture.returncode,
                        "native_block_entered": entered.is_set(),
                        "production_site": False,
                        "process_tree_restoration_proven": False,
                    },
                    indent=2,
                )
                + "\n"
            )
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            if client.state != "closed":
                session.close(
                    op.cleanup(
                        "finally-close", now=datetime.now(timezone.utc), seconds=10
                    ),
                    control=guard(10),
                )
        except BaseException as cleanup_error:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Installed browser and cleanup failed", [primary, cleanup_error]
                ) from None
            raise
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
