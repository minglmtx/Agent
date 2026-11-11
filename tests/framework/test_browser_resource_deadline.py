"""Marked actual native block inside a registered CPU step; never retry effects."""

from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import threading
import time
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_worker_fixtures import configuration
from browser_resource_fixtures import resource_case, Authority
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_linux_cgroups import actual_slurm_execution
from test_resource_journal import context


class ObservedClosure(Authority):
    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        assert termination is not None and termination.state == "reaped"
        assert termination.process_id == attempt.launcher_pid
        # Abrupt exit is not itself evidence of a dirty or clean domain.
        self.deny_close = step is None
        if step is not None:
            assert step.target == attempt.target
            data = json.loads(self.store.read(step.evidence, control=control))
            assert (
                data["target"] == step.target.model_dump(mode="json")
                and data["phase"] == "closed"
            )
        return super().verify_closed(
            spec, attempt, termination, step, operation, control
        )


def test_marked_native_deadline_keeps_original_resource_evidence(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _ = actual_slurm_execution()
    entered = threading.Event()
    saves: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.path == "/blocked":
                saves.append(self.path)
                self.wfile.write(b"entered")
                entered.set()
            else:
                self.wfile.write(
                    b"<html><button onclick=\"var r=new XMLHttpRequest();r.open('GET','/blocked',false);r.send();while(true){}\">Block</button></html>"
                )

    class EnteredDeadline:
        def __init__(self) -> None:
            self.overall = DeadlineControl(15, "native-before-entry")
            self.after: OperationControl | None = None

        def checkpoint(self) -> float:
            remaining = self.overall.checkpoint()
            if entered.is_set() and self.after is None:
                self.after = DeadlineControl(0.2, "native-after-entry")
            return (
                min(remaining, self.after.checkpoint())
                if self.after is not None
                else remaining
            )

        def wait(self, seconds: float) -> None:
            time.sleep(min(seconds, self.checkpoint(), 0.02))
            self.checkpoint()

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        thread.start()
        try:
            config = configuration(
                storage_installation(installed_sources),
                f"http://127.0.0.1:{server.server_port}/",
            )
            config = config.model_copy(
                update={
                    "spec": config.spec.model_copy(
                        update={
                            "scope": config.spec.scope.model_copy(
                                update={
                                    "owner": config.spec.scope.owner.model_copy(
                                        update={"job_id": execution.job_id}
                                    )
                                }
                            )
                        }
                    )
                }
            )
            c = resource_case(tmp_path, monkeypatch, config=config, real_step=True)
            c.authority = ObservedClosure(c.evidence)
            c.op = c.op.model_copy(
                update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=90)}
            )
            began = time.monotonic()
            with pytest.raises((OperationStopped, BaseExceptionGroup)) as caught:
                with registered_browser(
                    c.spec,
                    c.op,
                    journal=c.journal,
                    evidence=c.evidence,
                    controls=c.controls,
                    clock=c.clock,
                    authority=c.authority,
                ) as browser:
                    # Use the persisted public observation, never native page handles.
                    from lab_generate_skill.domain.observation import Observation

                    assert browser.observation_ref is not None
                    text = (
                        Observation.model_validate_json(
                            c.evidence.read(browser.observation_ref)
                        ).text
                        or ""
                    )
                    button = re.search(r"\[([^\]]+)\] button ['\"]Block['\"]", text)
                    assert button is not None
                    browser.step(
                        BrowserAction(
                            action_id="block",
                            protocol_id="browsergym-highlevel-v1",
                            name="click",
                            payload=f"click({button.group(1)!r})",
                        ),
                        context(c.spec.token, "block"),
                        control=EnteredDeadline(),
                    )
            failures = (
                list(caught.value.exceptions)
                if isinstance(caught.value, BaseExceptionGroup)
                else [caught.value]
            )
            assert (
                isinstance(failures[0], OperationStopped)
                and entered.is_set()
                and saves == ["/blocked"]
            )
            record = c.journal.read(
                c.spec.token,
                c.op.cleanup(
                    "inspect-ended", now=datetime.now(timezone.utc), seconds=30
                ),
            )
            ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))[
                "details"
            ]
            termination = ending["termination"]
            assert (
                termination["state"] == "reaped"
                and termination["kill_requested"] is True
            )
            assert record.state == "closed" and ending["step_closed"] is not None
            assert not ending["cleanup_errors"]
            assert ending["process_stop"]["worker_exit_observed"] is True
            assert ending["process_stop"]["supervisor_exit_observed"] is True
            assert ending["process_stop"]["worker_signal_requested"] is True
            assert time.monotonic() - began < 120
            (
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
                / "browser-resource-native-deadline.json"
            ).write_text(
                json.dumps(
                    {
                        "schema_version": "browser-resource-native-deadline-check/1",
                        "native_entered": True,
                        "action_calls": len(saves),
                        "terminal_state": record.state,
                        "ending": ending,
                        "production_authority": False,
                    },
                    indent=2,
                )
                + "\n"
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()
