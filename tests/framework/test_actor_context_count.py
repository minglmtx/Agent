"""Native count RPC shares ownership and hard gates; synthetic tokenizer only."""

import io
import json
from pathlib import Path
from typing import Any, cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_count_protocol import (
    ActorCountCommand,
    ActorCountReply,
    decode_worker_command,
    decode_count_reply,
)
from lab_generate_skill.adapters.models.actor_worker_protocol import (
    ActorWorkerCommand,
    decode_reply,
    MAX_WORKER_PACKET,
)
from lab_generate_skill.adapters.models.actor_worker_stream import serve
from lab_generate_skill.adapters.processes.framing import frame
from lab_generate_skill.adapters.processes.stream_frames import read_frame
from lab_generate_skill.domain.actor_context_count import ActorTokenCount
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_worker_fixtures import worker_case
from test_actor_worker import commands
from test_slurm_commands import guard


@pytest.mark.parametrize("count", [1, 99, 100, 101, 201, 40000])
def test_exact_count_does_not_truncate_or_infer_and_keeps_hard_gate(
    tmp_path: Path, count: int
) -> None:
    engine, loader, prompt, params, control, service, channel, client = worker_case(
        tmp_path
    )
    loader.session.tokens = (1,) * count
    measured = client.measure(prompt, params, control)
    measured.verify(prompt, params, engine.artifact, engine.config)
    assert measured.input_tokens == count
    assert client.measure(prompt, params, control) == measured
    assert loader.loads == 1 and loader.session.calls == 0 and not service.closed
    if count > 100:
        with pytest.raises(ActorInputBudgetExceeded):
            client.validate(prompt, params, control)
        with pytest.raises(ActorInputBudgetExceeded):
            client.generate(prompt, params, control)
        assert loader.session.calls == 0 and channel.aborts == 0
    else:
        client.validate(prompt, params, control)
    client.close(control)
    assert loader.session.closed == 1 and channel.finishes == 1
    parsed = [decode_worker_command(raw) for raw in channel.sent]
    assert [c.sequence for c in parsed] == list(range(1, len(parsed) + 1))
    assert sum(c.operation == "configure" for c in parsed) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"sequence": 1},
        {"sequence": 10000},
        {"sequence": True},
        {"remaining_seconds": 0},
        {"remaining_seconds": float("nan")},
        {"remaining_seconds": True},
        {"parameters": None},
        {"request": None},
        {"operation": "generate"},
        {"artifact": {}},
        {"schema_version": "actor-context-count-command/2"},
    ],
)
def test_count_contract_rejects_illegal_or_configure_fields(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    _, _, prompt, params, _, _, _, _ = worker_case(tmp_path)
    command = ActorCountCommand(
        session_id="session",
        sequence=2,
        remaining_seconds=5,
        request=prompt,
        parameters=params,
    )
    with pytest.raises(ValidationError):
        ActorCountCommand.model_validate({**command.model_dump(), **change})


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"null",
        b"\xff",
        b'{"schema_version":"x","schema_version":"y"}',
        b'{"schema_version":NaN}',
    ],
)
def test_unknown_empty_duplicate_and_wrong_wire_are_rejected(raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        decode_worker_command(raw)


@pytest.mark.parametrize("fault", ["repeat", "skip", "session", "unconfigured"])
def test_count_and_generation_share_sequence_and_configuration(
    tmp_path: Path, fault: str
) -> None:
    configure, generate, _, loader, service = commands(tmp_path)
    assert generate.request is not None and generate.parameters is not None
    command = ActorCountCommand(
        session_id="session",
        sequence=2,
        remaining_seconds=5,
        request=generate.request,
        parameters=generate.parameters,
    )
    if fault != "unconfigured":
        assert service.handle(configure).status == "ok"
        assert service.handle(command).status == "ok"
    bad = (
        command.model_copy(
            update={"sequence": 4 if fault == "skip" else 3, "session_id": "other"}
        )
        if fault == "session"
        else command.model_copy(update={"sequence": 4}) if fault == "skip" else command
    )
    assert service.handle(bad).status == "error" and service.closed
    assert loader.session.calls == 0
    assert loader.loads == (0 if fault == "unconfigured" else 1)


@pytest.mark.parametrize(
    "field",
    [
        "input_sha256",
        "model_input_sha256",
        "parameters_sha256",
        "artifact_sha256",
        "engine_config_sha256",
        "tokenizer_sha256",
        "template_sha256",
        "context_window",
    ],
)
def test_foreign_native_count_fails_closed_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    _, loader, prompt, params, control, service, channel, client = worker_case(tmp_path)
    client.configure(control)
    original = channel.exchange

    def foreign(payload: bytes, supplied: OperationControl) -> bytes:
        raw = original(payload, supplied)
        data = json.loads(raw)
        data["measurement"][field] = 201 if field == "context_window" else "0" * 64
        return (
            ActorCountReply.model_validate_json(json.dumps(data))
            .model_dump_json()
            .encode()
        )

    monkeypatch.setattr(channel, "exchange", foreign)
    with pytest.raises(ValueError):
        client.measure(prompt, params, control)
    assert service.closed and channel.aborts == 1 and loader.session.calls == 0
    before = len(channel.sent)
    with pytest.raises(OwnershipConflict):
        client.measure(prompt, params, control)
    assert len(channel.sent) == before


@pytest.mark.parametrize("fault", ["lost", "cancel", "partial"])
def test_count_return_failure_closes_original_and_never_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    _, loader, prompt, params, control, service, channel, client = worker_case(tmp_path)
    client.configure(control)
    original = channel.exchange

    class StopAfterReturn:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise OperationStopped("CANCELLED", "count-return")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    stopped = StopAfterReturn()

    def fail(payload: bytes, supplied: OperationControl) -> bytes:
        raw = original(payload, supplied)
        if fault == "lost":
            raise OSError("count return lost")
        if fault == "partial":
            return raw[:-1]
        stopped.stopped = True
        return raw

    monkeypatch.setattr(channel, "exchange", fail)
    with pytest.raises((OSError, ValueError, OperationStopped)) as caught:
        client.measure(prompt, params, stopped if fault == "cancel" else control)
    if fault == "cancel":
        assert getattr(caught.value, "actor_worker_reply").measurement.input_tokens == 3
    assert loader.loads == loader.session.closed == 1 and loader.session.calls == 0
    assert service.closed and channel.aborts == 1
    with pytest.raises(OwnershipConflict):
        client.measure(prompt, params, guard())
    assert (
        sum(decode_worker_command(raw).operation == "measure" for raw in channel.sent)
        == 1
    )


def test_mixed_stream_keeps_original_generation_wire(tmp_path: Path) -> None:
    configure, generate, close, loader, service = commands(tmp_path)
    assert generate.request is not None and generate.parameters is not None
    count = ActorCountCommand(
        session_id="session",
        sequence=2,
        remaining_seconds=5,
        request=generate.request,
        parameters=generate.parameters,
    )
    generate = ActorWorkerCommand.model_validate(
        generate.model_copy(update={"sequence": 3})
    )
    close = ActorWorkerCommand.model_validate(close.model_copy(update={"sequence": 4}))
    output = io.BytesIO()
    serve(
        service,
        io.BytesIO(
            b"".join(
                frame(c.model_dump_json().encode(), MAX_WORKER_PACKET)
                for c in (configure, count, generate, close)
            )
        ),
        output,
    )
    stream = io.BytesIO(output.getvalue())
    for command in (configure, count, generate, close):
        raw = read_frame(stream, MAX_WORKER_PACKET)
        assert raw is not None
        if isinstance(command, ActorCountCommand):
            assert decode_count_reply(command, raw).status == "ok"
        else:
            assert decode_reply(command, raw).schema_version == "actor-worker-reply/1"
    assert loader.session.calls == loader.session.closed == 1


@pytest.mark.parametrize("value", [0, -1, True, 2147483648, "3", None])
def test_native_count_strict_type_and_range(tmp_path: Path, value: object) -> None:
    engine, _, prompt, params, control, _, _, _ = worker_case(tmp_path)
    result = engine.measure(prompt, params, control)
    with pytest.raises(ValidationError):
        ActorTokenCount.model_validate({**result.model_dump(), "input_tokens": value})
    engine.close(control)


@pytest.mark.parametrize("tokens", [(), (True,), (-1,), ("1",), [1, 2]])
def test_invalid_native_tokenization_fails_closed(
    tmp_path: Path, tokens: object
) -> None:
    _, loader, prompt, params, control, service, channel, client = worker_case(tmp_path)
    loader.session.tokens = cast(tuple[int, ...], tokens)
    from lab_generate_skill.adapters.models.actor_worker_client import (
        ActorWorkerFailure,
    )

    with pytest.raises(ActorWorkerFailure):
        client.measure(prompt, params, control)
    assert loader.session.calls == 0 and loader.session.closed == 1
    assert service.closed and channel.aborts == 1


def test_count_cancel_before_send_has_no_effect(tmp_path: Path) -> None:
    _, loader, prompt, params, _, _, channel, client = worker_case(tmp_path)
    with pytest.raises(OperationStopped):
        client.measure(prompt, params, guard(0.000000001))
    assert not channel.sent and loader.loads == 0
    client.close(guard())
