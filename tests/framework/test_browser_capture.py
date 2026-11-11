"""Original browser read request, durable intent and no new observation/action."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.adapters.browsergym.worker_protocol import (
    decode_command,
    decode_reply,
    BrowserWorkerCommand,
)
from evidence_control_fixtures import EvidenceFixtureStore
from browser_worker_fixtures import case as worker_case
from browsergym_fixtures import operation
from test_slurm_commands import guard


class Authority:
    def __init__(self, store: EvidenceFixtureStore) -> None:
        self.store, self.denied = store, False

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        intent = BrowserCaptureIntent.model_validate_json(
            self.store.read(intent_ref, control)
        )
        assert intent.request == request
        assert (
            intent.configuration_sha256
            == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        )
        if self.denied:
            raise PermissionError("capture denied")


def capture_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    engine, service, channel, client = worker_case()
    initial = client.start(operation(client.spec, "start"), control=guard())
    req = BrowserCaptureRequest(
        scope=client.spec.scope,
        operation=operation(client.spec, "capture"),
        observation_sha256=hashlib.sha256(
            initial.observation.model_dump_json().encode()
        ).hexdigest(),
        collector_id="admin-page-health",
        collector_version="1",
    )
    monkeypatch.setattr(engine, "last_capture", None, raising=False)

    def capture(
        request: BrowserCaptureRequest, *, control: OperationControl
    ) -> BrowserCaptureResult:
        engine.calls.append("capture")
        if engine.failure is not None:
            raise engine.failure
        result = BrowserCaptureResult(
            request_sha256=request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result='{"health":true}',
        )
        monkeypatch.setattr(engine, "last_capture", result)
        return result

    monkeypatch.setattr(engine, "capture_page", capture, raising=False)
    store = EvidenceFixtureStore(tmp_path)
    authority = Authority(store)
    recorder = RecordedBrowserCapture(client, store, authority)
    return engine, service, channel, client, store, authority, recorder, req, initial


@pytest.mark.parametrize("terminal", [False, True])
def test_private_capture_preserves_observation_and_terminal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, terminal: bool
) -> None:
    engine, service, channel, client, store, authority, recorder, req, initial = (
        capture_case(tmp_path, monkeypatch)
    )
    if terminal:
        client.state = "terminal"
    ref = recorder.capture(req, control=guard())
    assert BrowserCaptureResult.model_validate_json(store.read(ref)) == recorder.result
    assert client.last_readout == initial and client.state == (
        "terminal" if terminal else "ready"
    )
    command = decode_command(channel.calls[-1])
    assert (
        command.schema_version == "browser-worker-command/3"
        and command.capture_request == req
    )
    assert engine.calls == ["start", "capture"]
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        client.capture_page(req, recorder.intent_ref, authority, control=guard())
    with pytest.raises(InvalidTransition):
        recorder.capture(req, control=guard())
    assert len(channel.calls) == before
    service.close()


@pytest.mark.parametrize(
    "fault",
    [
        "denied",
        "observation",
        "scope",
        "native",
        "wire",
        "intent-after",
        "result-after",
        "result-readback",
    ],
)
def test_capture_fault_keeps_original_and_never_resends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    engine, service, channel, client, raw_store, authority, recorder, req, initial = (
        capture_case(tmp_path, monkeypatch)
    )
    store: EvidenceFixtureStore = raw_store
    if fault == "denied":
        authority.denied = True
    if fault == "observation":
        req = req.model_copy(update={"observation_sha256": "f" * 64})
    if fault == "scope":
        req = req.model_copy(
            update={"scope": req.scope.model_copy(update={"context_id": "foreign"})}
        )
    if fault == "native":
        engine.failure = OSError("native read failed")
    if fault == "wire":
        channel.bad_reply = b"{}"
    original_put, original_read = store.put, store.read
    target = (
        "browser-capture-intent/1"
        if fault.startswith("intent")
        else "browser-capture-result/1"
    )

    def put(data: bytes, metadata: Any, control: Any) -> EvidenceRef:
        ref = original_put(data, metadata, control)
        if metadata.content_schema == target and fault.endswith("after"):
            raise OSError("publication lost acknowledgement")
        return ref

    def read(ref: EvidenceRef, control: Any = None) -> bytes:
        if ref.content_schema == target and fault.endswith("readback"):
            return b"{}"
        return original_read(ref, control)

    monkeypatch.setattr(store, "put", put)
    monkeypatch.setattr(store, "read", read)
    with pytest.raises(
        (
            PermissionError,
            OwnershipConflict,
            OSError,
            ValueError,
            BrowserWorkerFailure,
            EvidenceIntegrityError,
        )
    ) as caught:
        recorder.capture(req, control=guard())
    assert getattr(caught.value, "capture_returned_result") == recorder.result
    assert client.last_readout == initial
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        recorder.capture(req, control=guard())
    assert len(channel.calls) == before
    assert engine.calls[:2] == (
        ["start", "capture"]
        if fault in ("native", "wire", "result-after", "result-readback")
        else ["start"]
    )
    service.close()


@pytest.mark.parametrize(
    "change",
    ["request", "intent", "operation", "old_command", "old_reply", "foreign_reply"],
)
def test_capture_wire_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    _, service, channel, client, _, _, recorder, req, _ = capture_case(
        tmp_path, monkeypatch
    )
    recorder.capture(req, control=guard())
    command = decode_command(channel.calls[-1])
    data = command.model_dump()
    if change == "request":
        data["capture_request"] = None
    elif change == "intent":
        data["capture_intent_ref"] = None
    elif change == "operation":
        data["operation"]["operation_id"] = "foreign"
    elif change == "old_command":
        data["schema_version"] = "browser-worker-command/1"
    else:
        reply = client.last_reply
        assert reply is not None and reply.captured is not None
        update = (
            {"schema_version": "browser-worker-reply/1"}
            if change == "old_reply"
            else {
                "captured": reply.captured.model_copy(
                    update={"request_sha256": "f" * 64}
                )
            }
        )
        with pytest.raises(ValueError):
            decode_reply(
                command,
                client.spec,
                reply.model_copy(update=update).model_dump_json().encode(),
            )
        service.close()
        return
    with pytest.raises(ValueError):
        BrowserWorkerCommand.model_validate(data)
    service.close()
