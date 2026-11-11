"""Actual resource/trace/browser CPU step; model and business rights are fixtures.

Original resource-domain closure is observed; separate authority denial must
still quarantine. No production website/model call or restoration claim.
"""

from dataclasses import asdict
from contextlib import nullcontext
from lab_generate_skill.domain.browser_step import BrowserStepClosed
from test_linux_cgroups import actual_slurm_execution
import state_contract_fixtures
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import signal
import threading
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.application.browser_action import (
    execute_browser_action,
    BrowserDispatchFailure,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout, BrowserSessionSpec
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
    BrowserResourceAttempt,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.initial_observation import BrowserAcquiredFact
from lab_generate_skill.domain.browser_dispatch import BrowserDispatch
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.trace_events import (
    GenerationIntent,
    GenerationPlanned,
    GenerationObserved,
    ActionPlanned,
    InteractionObserved,
    TraceProgressEvent,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case, Authority
from browser_worker_fixtures import configuration
from trace_journal_fixtures import fixture as trace_fixture, UnitLiveTraceAuthority
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_run_journal import command
from test_resource_journal import context
from source_review_records import ReadOnlyEvidence, review_resource
from lab_generate_skill.adapters.processes.deadline import DeadlineControl


class ActualReturnAuthority(UnitLiveTraceAuthority):
    def verify_event(
        self,
        snapshot: TraceSnapshot,
        event: TraceProgressEvent,
        operation: OperationContext,
    ) -> None:
        if not isinstance(event, InteractionObserved):
            super().verify_event(snapshot, event, operation)
            return
        result = event.interaction.result
        assert result is not None
        returned = BrowserReadout.model_validate_json(
            self.store.read(result.return_ref)
        )
        observed = Observation.model_validate_json(
            self.store.read(result.observation_ref)
        )
        if (
            returned.observation != observed
            or returned.action != event.interaction.action
            or returned.operation != event.interaction.operation
            or returned.scope != event.interaction.scope
        ):
            raise OwnershipConflict("Actual browser evidence changed original trace")


class EngineeringTreeAuthority(Authority):
    def verify_started(
        self,
        spec: BrowserResourceSpec,
        started: BrowserResourceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify_started(spec, started, operation, control)
        worker = started.owner_guard.worker
        assert (
            parse_process_start(
                Path(f"/proc/{worker.process_id}/stat").read_bytes(), worker.process_id
            )
            == worker.start_ticks
        )

    def verify_closed(
        self,
        spec: BrowserResourceSpec,
        attempt: BrowserResourceAttempt,
        termination: ProcessTermination | None,
        step: BrowserStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        assert attempt.prepared is not None and attempt.prepared_ref is not None
        assert json.loads(self.store.read(attempt.prepared_ref, control=control)) == (
            attempt.prepared.model_dump(mode="json")
        )
        assert termination is not None and termination.state == "reaped"
        assert termination.process_id == attempt.launcher_pid
        assert not termination.cleanup_errors
        # A transport failure uses the existing supervised abort path. Its
        # launcher can be killed, but this alone never proves its tree closed.
        # Retain the exact abort fact and require the full original step below.
        assert termination.returncode == 0 or (
            termination.returncode == -signal.SIGKILL and termination.kill_requested
        )
        assert step is not None and step.target == attempt.target
        raw = json.loads(self.store.read(step.evidence, control=control))
        assert isinstance(raw, dict)
        assert (
            raw["schema_version"] == "browser-step-raw/1" and raw["phase"] == "closed"
        )
        assert raw["target"] == step.target.model_dump(mode="json")
        assert isinstance(raw["kernel"], list) and raw["kernel"]
        assert all(isinstance(observation, dict) for observation in raw["kernel"])
        assert isinstance(raw["commands"], list) and raw["commands"]
        assert raw["error"] is None
        assert all(
            isinstance(command, dict)
            and command.get("complete") is True
            and type(command.get("returncode")) is int
            and command["returncode"] == 0
            for command in raw["commands"]
        )
        proof = self.store.put(
            json.dumps(
                {
                    "schema_version": "engineering-browser-close/1",
                    "attempt": attempt.model_dump(mode="json"),
                    "termination": asdict(termination),
                    "original_step_verified": True,
                    "step_closed": step.model_dump(mode="json"),
                }
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="engineering-browser-close/1",
                visibility="private",
                producer="actual-loopback-engineering",
            ),
            control=control,
        )
        return ClosureReceipt(
            token=spec.token,
            operation_id=operation.operation_id,
            status="unconfirmed" if self.deny_close else "closed",
            evidence=(proof,),
        )


@pytest.mark.parametrize("deny_closure", [False, True])
def test_installed_resource_trace_save_once_and_original_step_closure(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deny_closure: bool,
) -> None:
    execution, _ = actual_slurm_execution()
    trace_scope = state_contract_fixtures.scope()
    trace_scope = trace_scope.model_copy(
        update={
            "owner": trace_scope.owner.model_copy(update={"job_id": execution.job_id})
        }
    )
    monkeypatch.setattr("trace_fixtures.scope", lambda: trace_scope)
    trace_root = tmp_path / "trace"
    trace_root.mkdir()
    data = trace_fixture(trace_root, outcomes=("returned",))
    scope = data.plan.scope
    saves: list[bytes] = []
    workers_before_get: list[BrowserWorkerAcquiredFact] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            # The real first HTTP request must already have durable original
            # worker ownership, before Chromium can return an initial page.
            record = c.journal.read(c.spec.token, c.op)
            assert record.state == "acquired"
            acquired = BrowserWorkerAcquiredFact.model_validate_json(
                c.evidence.read(record.events[-1].evidence[0])
            )
            acquired.check_spec(c.spec)
            workers_before_get.append(acquired)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Product</title><form method='post'><input name='description' value='Updated'><button type='submit'>Save</button></form></html>"
            )

        def do_POST(self) -> None:
            saves.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>Saved</title><p>Updated description saved</p></html>"
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = configuration(
            storage_installation(installed_sources),
            f"http://127.0.0.1:{server.server_port}/",
        )
        public = PublicTask(
            identity=scope.task,
            goal="Save the prepared description",
            start_url=config.spec.task.start_url,
            allowed_actions=("click",),
        )
        browser_spec = BrowserSessionSpec.model_validate(
            {**config.spec.model_dump(), "scope": scope, "task": public}
        )
        config = config.model_copy(update={"spec": browser_spec})
        resource_root = tmp_path / "resource"
        resource_root.mkdir()
        c = resource_case(
            resource_root, monkeypatch, config=config, store=data.store, real_step=True
        )
        monkeypatch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            FramedProcessSession,
        )
        c.authority = EngineeringTreeAuthority(data.store)
        c.authority.deny_close = deny_closure
        c.op = c.op.model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=90)}
        )

        def put(value: object, schema: str) -> EvidenceRef:
            return data.store.put(
                json.dumps(value).encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema=schema,
                    visibility="private",
                    producer="synthetic-actor-fixture",
                ),
            )

        after = None
        client = None
        trace_journal = None
        with (
            pytest.raises(BaseExceptionGroup) if deny_closure else nullcontext()
        ) as closing:
            with registered_browser(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=c.authority,
            ) as browser:
                assert browser.observation_ref is not None
                assert browser.resource_started_ref is not None and workers_before_get
                initial_fact = BrowserAcquiredFact.model_validate_json(
                    c.evidence.read(browser.resource_started_ref)
                )
                assert (
                    initial_fact.details.started.owner_guard
                    == workers_before_get[0].details.prepared.owner_guard
                )
                assert isinstance(browser.engine, SupervisedBrowserSession)
                client = browser.engine
                initial = client.last_readout
                assert initial is not None
                bid = re.search(
                    r"\[([^\]]+)\] button ['\"]Save['\"]",
                    initial.observation.text or "",
                )
                assert bid
                action = BrowserAction(
                    action_id="save",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({bid.group(1)!r})",
                )
                plan = TracePlan.model_validate(
                    {
                        **data.plan.model_dump(),
                        "initial_observation_ref": browser.observation_ref,
                    }
                )
                trace_journal = FileTraceJournal(
                    trace_root / "journal",
                    plan,
                    c.controls,
                    data.store,
                    ActualReturnAuthority(data.store),
                )
                trace_journal.create(
                    plan, command("trace-create", attempt=scope.attempt_id)
                )
                old = data.data.trace.turns[0].generation
                gen = ActorGeneration.model_validate(
                    {
                        **old.model_dump(),
                        "before_observation_ref": browser.observation_ref,
                        "input_ref": put(
                            {
                                "request_id": old.request_id,
                                "before": browser.observation_ref.model_dump(
                                    mode="json"
                                ),
                            },
                            "actor-model-input/1",
                        ),
                        "response_ref": put(
                            {
                                "generation_id": old.generation_id,
                                "action": action.model_dump(mode="json"),
                            },
                            "actor-model-response/1",
                        ),
                    }
                )
                intent = GenerationIntent.model_validate(
                    {
                        "schema_version": (
                            "actor-generation-intent/2"
                            if gen.schema_version == "actor-generation/2"
                            else "actor-generation-intent/1"
                        ),
                        **{
                            key: value
                            for key, value in gen.model_dump(
                                exclude={"schema_version"}
                            ).items()
                            if key in GenerationIntent.model_fields
                        },
                    }
                )
                events: tuple[TraceProgressEvent, ...] = (
                    GenerationPlanned(
                        operation=command(
                            "generation-intent", attempt=scope.attempt_id
                        ),
                        intent=intent,
                    ),
                    GenerationObserved(
                        operation=command(
                            "generation-result", attempt=scope.attempt_id
                        ),
                        generation=gen,
                    ),
                )
                for revision, event in enumerate(events):
                    trace_journal.append(event, revision, event.operation)
                execute = context(c.spec.token, "actual-save")
                request = BrowserDispatch(
                    intent=ActionPlanned(
                        operation=command("action-intent", attempt=scope.attempt_id),
                        decision=ActorDecision(
                            generation_id=gen.generation_id,
                            outcome="action",
                            action=action,
                        ),
                        execution_operation=execute,
                    ),
                    expected_revision=2,
                    result_operation=execute.cleanup(
                        "record-save", now=datetime.now(timezone.utc), seconds=30
                    ),
                )
                original = client.step

                def checked(
                    action: BrowserAction,
                    operation: OperationContext,
                    *,
                    control: OperationControl,
                ) -> BrowserReadout:
                    persisted = trace_journal.read(
                        command("inspect-original-intent", attempt=scope.attempt_id)
                    )
                    assert persisted.events[-1] == request.intent
                    assert (
                        c.journal.read(
                            c.spec.token, context(c.spec.token, "inspect-resource")
                        ).state
                        == "acquired"
                    )
                    return original(action, operation, control=control)

                monkeypatch.setattr(client, "step", checked)
                after = execute_browser_action(
                    request, trace_journal, browser, c.controls
                )
                assert (
                    after.revision == 4
                    and after.project().interactions == 1
                    and saves == [b"description=Updated"]
                )
                assert (
                    client.last_readout is not None
                    and client.last_readout.observation.tabs[0].title == "Saved"
                )
                with pytest.raises(BrowserDispatchFailure) as repeated:
                    execute_browser_action(request, trace_journal, browser, c.controls)
                assert (
                    isinstance(repeated.value.primary, DispatchAlreadyCommitted)
                    and saves == [b"description=Updated"]
                    and client.sequence == 3
                )
        assert client is not None and after is not None and trace_journal is not None
        assert (
            client.channel.capture.termination is not None
            and client.channel.capture.termination.returncode == 0
        )
        record = c.journal.read(
            c.spec.token,
            c.op.cleanup("inspect-ended", now=datetime.now(timezone.utc), seconds=30),
        )
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "quarantined" if deny_closure else "closed",
        ]
        if closing is not None:
            assert (
                getattr(closing.value, "browser_resource_ending_ref")
                == record.events[-1].evidence[0]
            )
        assert (
            trace_journal.read(
                command("read-trace-after-close", attempt=scope.attempt_id)
            )
            == after
        )
        with pytest.raises(DispatchAlreadyCommitted):
            with registered_browser(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=c.authority,
            ):
                pytest.fail("must not reacquire quarantined allocation")
        assert saves == [b"description=Updated"]
        if not deny_closure:
            reviewed = review_resource(
                record.model_dump(mode="json"),
                c.spec.token,
                ReadOnlyEvidence(trace_root / "evidence"),
                DeadlineControl(15, "browser-original-independent-review"),
            )
            assert reviewed["target"] == workers_before_get[
                0
            ].details.prepared.step.controller.target.model_dump(mode="json")
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output:
            (Path(output) / f"browser-resource-trace-{deny_closure}.json").write_text(
                json.dumps(
                    {
                        "resource": record.model_dump(mode="json"),
                        "trace": after.model_dump(mode="json"),
                        "actual_posts": len(saves),
                        "returncode": client.channel.capture.returncode,
                        "production_site": False,
                        "synthetic_actor": True,
                        "original_step_verified": True,
                        "worker_acquired_before_actual_get": [
                            w.model_dump(mode="json") for w in workers_before_get
                        ],
                        "closure_authority_denied": deny_closure,
                    },
                    indent=2,
                )
                + "\n"
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
