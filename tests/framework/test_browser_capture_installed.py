"""Registered fixed browser capture on controlled pages; no task/model success."""

from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminPageHealth
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from browser_worker_fixtures import configuration
from browser_resource_fixtures import resource_case
from test_browser_resource_installed import EngineeringTreeAuthority
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard


def test_registered_browser_captures_current_page_without_new_observation(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"""<html><title>Controlled page health</title><main>Ready</main>
<button onclick="document.querySelector('main').innerHTML='<form id=login-form><input type=password></form>'">Login control</button>
<button onclick="document.querySelector('main').innerText='404 page'">Error control</button></html>"""
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        formal_source_admission=False,
        actual_actor_calls=0,
        captures=[],
    )
    try:
        base = configuration(
            storage_installation(installed_sources),
            f"http://127.0.0.1:{server.server_port}/",
        )
        identity = base.spec.task.identity.model_copy(
            update={
                "site": "shopping_admin",
                "family": "product_description",
                "contract_version": 1,
            }
        )
        scope = base.spec.scope.model_copy(
            update={
                "task": identity,
                "owner": base.spec.scope.owner.model_copy(
                    update={"job_id": execution.job_id}
                ),
            }
        )
        public = base.spec.task.model_copy(
            update={
                "identity": identity,
                "goal": "Controlled page-health fixture; not a task attempt",
            }
        )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": base.spec.model_copy(update={"scope": scope, "task": public}),
            }
        )
        c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
        c.op = c.op.model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=120)}
        )
        c.authority = EngineeringTreeAuthority(c.evidence)

        class Authority:
            def verify_capture(
                self,
                configuration: BrowserWorkerConfiguration,
                request: BrowserCaptureRequest,
                intent_ref: EvidenceRef,
                control: OperationControl,
            ) -> None:
                assert configuration == c.spec.configuration and request.scope == scope
                intent = BrowserCaptureIntent.model_validate_json(
                    c.evidence.read(intent_ref, control)
                )
                assert intent.request == request
                assert (
                    intent.configuration_sha256
                    == hashlib.sha256(
                        configuration.model_dump_json().encode()
                    ).hexdigest()
                )
                op = c.op.model_copy(
                    update={"operation_id": "read-" + request.operation.operation_id}
                )
                assert c.journal.read(c.spec.token, op).state == "acquired"
                control.checkpoint()

        with registered_browser(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
        ) as browser:
            assert isinstance(browser.engine, SupervisedBrowserSession)
            client = browser.engine

            def capture(label: str, expected: tuple[bool, bool]) -> None:
                before = client.last_readout
                assert before is not None and browser.observation_ref is not None
                req = BrowserCaptureRequest(
                    scope=scope,
                    operation=c.op.model_copy(
                        update={"operation_id": "capture-" + label}
                    ),
                    observation_sha256=browser.observation_ref.sha256,
                    collector_id="admin-page-health",
                    collector_version="1",
                )
                recorder = RecordedBrowserCapture(client, c.evidence, Authority())
                ref = recorder.capture(req, control=guard(20))
                result = BrowserCaptureResult.model_validate_json(
                    c.evidence.read(ref, guard(10))
                )
                health = AdminPageHealth.model_validate_json(result.private_result)
                assert (
                    health.login,
                    health.page_error,
                ) == expected and health.url == public.start_url
                assert (
                    client.last_readout == before
                    and browser.observation_ref.sha256 == req.observation_sha256
                )
                assert recorder.intent_ref is not None
                facts["captures"].append(
                    dict(
                        request=req.model_dump(mode="json"),
                        intent_ref=recorder.intent_ref.model_dump(mode="json"),
                        result_ref=ref.model_dump(mode="json"),
                        health=health.model_dump(mode="json"),
                        observation_sequence=before.observation.sequence,
                    )
                )

            capture("initial", (False, False))
            for number, label, expected in [
                (1, "Login control", (True, False)),
                (2, "Error control", (False, True)),
            ]:
                assert client.last_readout is not None
                match = re.search(
                    r"\[([^\]]+)\] button ['\"]" + label + r"['\"]",
                    client.last_readout.observation.text or "",
                )
                assert match
                action = BrowserAction(
                    action_id="control-" + str(number),
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({match.group(1)!r})",
                )
                browser.step(
                    action,
                    c.op.model_copy(update={"operation_id": action.action_id}),
                    control=guard(20),
                )
                capture("after-" + str(number), expected)
            terminal = BrowserAction(
                action_id="terminal",
                protocol_id="browsergym-highlevel-v1",
                name="send_msg_to_user",
                payload="send_msg_to_user('fixture done')",
            )
            ending = browser.step(
                terminal,
                c.op.model_copy(update={"operation_id": "terminal"}),
                control=guard(20),
            )
            assert ending.terminal
            capture("terminal", (False, True))
            assert client.state == "terminal" and client.last_readout is not None
            assert client.last_readout.observation.sequence == 3
            facts["terminal_return_ref"] = ending.return_ref.model_dump(mode="json")
        record = c.journal.read(
            c.spec.token,
            c.op.cleanup("read-closed", now=datetime.now(timezone.utc), seconds=20),
        )
        assert record.state == "closed"
        closed = json.loads(c.evidence.read(record.events[-1].evidence[0], guard(10)))
        assert not closed["details"]["cleanup_errors"]
        facts.update(
            passed=True,
            resource=record.model_dump(mode="json"),
            ending=closed,
            controlled_browser_actions=3,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "browser-page-capture-native.json"
        ).write_text(json.dumps(facts, indent=2) + "\n")
