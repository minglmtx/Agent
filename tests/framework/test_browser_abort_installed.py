"""Real loopback timeout and original CPU-domain proof, without model/source IO."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import threading
import pytest
from browser_resource_fixtures import resource_case
from browser_closure_fixtures import controlled_timeout_configuration
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_browser_resource_installed import EngineeringTreeAuthority
from test_linux_cgroups import actual_slurm_execution
from source_review_records import ReadOnlyEvidence, review_resource
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped


def test_installed_action_timeout_closes_original_tree_without_resending(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    release = threading.Event()
    received = threading.Event()
    posts: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Pending</title><form method='post'><button type='submit'>Hold</button></form></html>"
            )

        def do_POST(self) -> None:
            posts.append(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            received.set()
            # Return no response while the original action deadline expires.
            # Cleanup releases this handler; it never resends or changes state.
            release.wait(60)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = controlled_timeout_configuration(
            storage_installation(installed_sources),
            execution.job_id,
            f"http://127.0.0.1:{server.server_port}/",
        )
        c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
        c.authority = EngineeringTreeAuthority(c.evidence)
        c.op = c.op.model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=120)}
        )
        with registered_browser(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
        ) as browser:
            client = browser.engine
            assert isinstance(client, SupervisedBrowserSession)
            initial = client.last_readout
            assert initial is not None and browser.observation_ref is not None
            bid = re.search(
                r"\[([^\]]+)\] button ['\"]Hold['\"]", initial.observation.text or ""
            )
            assert bid is not None
            action = BrowserAction(
                action_id="original-timeout",
                protocol_id="browsergym-highlevel-v1",
                name="click",
                payload=f"click({bid.group(1)!r})",
            )
            operation = c.op.model_copy(
                update={
                    "operation_id": "original-bounded-action",
                    "deadline": datetime.now(timezone.utc) + timedelta(seconds=5),
                }
            )
            with pytest.raises(OperationStopped) as failed:
                browser.step(action, operation, control=c.controls.bind(operation))
            assert received.is_set() and len(posts) == 1
            assert client.transport_failed and client.state == "quarantined"
            assert browser.last_return_ref is None
            assert failed.value.reason_code == "DEADLINE_EXCEEDED"
            sequence = client.sequence
            with pytest.raises(InvalidTransition):
                browser.step(action, operation, control=c.controls.bind(operation))
            assert client.sequence == sequence and len(posts) == 1
        termination = client.channel.capture.termination
        assert termination is not None
        assert termination.state == "reaped" and termination.returncode == -9
        assert termination.kill_requested and not termination.cleanup_errors
        inspect = c.op.cleanup(
            "inspect-original-close", now=datetime.now(timezone.utc), seconds=30
        )
        record = c.journal.read(c.spec.token, inspect)
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        reviewed = review_resource(
            record.model_dump(mode="json"),
            c.spec.token,
            ReadOnlyEvidence(tmp_path / "evidence"),
            DeadlineControl(15, "readonly-original-abort-close"),
        )
        assert len(posts) == 1 and browser.engine.state == "closed"
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output:
            (Path(output) / "browser-controlled-timeout-closure.json").write_text(
                json.dumps(
                    {
                        "resource": record.model_dump(mode="json"),
                        "independent_original_domain_review": reviewed,
                        "actual_posts": len(posts),
                        "original_response": "unknown",
                        "original_error": {
                            "type": type(failed.value).__name__,
                            "reason": failed.value.reason_code,
                        },
                        "launcher_returncode": termination.returncode,
                        "kill_requested": termination.kill_requested,
                        "safe_Reset_or_business_acceptance": False,
                        "model_source_database_paid_calls": 0,
                    },
                    indent=2,
                )
                + "\n"
            )
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
