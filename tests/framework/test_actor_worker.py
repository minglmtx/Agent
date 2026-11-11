"""Ordered worker service/client, bounds, rejection, wire faults and cleanup."""

import io
import json
import struct
from pathlib import Path
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_worker_protocol import (
    ActorWorkerCommand,
    ActorWorkerReply,
    MAX_WORKER_PACKET,
    decode_command,
    decode_reply,
)
from lab_generate_skill.adapters.models.actor_worker_client import (
    ActorWorkerFailure,
)
from lab_generate_skill.adapters.models.actor_worker_stream import serve
from lab_generate_skill.adapters.processes.framing import frame
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    OperationStopped,
    OwnershipConflict,
)
from actor_worker_fixtures import worker_case
from actor_engine_fixtures import Loader
from lab_generate_skill.adapters.models.actor_service import ActorService


def commands(
    root: Path,
) -> tuple[
    ActorWorkerCommand,
    ActorWorkerCommand,
    ActorWorkerCommand,
    Loader,
    ActorService,
]:
    engine, loader, request, parameters, control, service, channel, client = (
        worker_case(root)
    )
    configure = ActorWorkerCommand(
        session_id="session",
        sequence=1,
        operation="configure",
        controller=current_process_identity(),
        remaining_seconds=5,
        artifact=engine.artifact,
        config=engine.config,
        installation=client._installation,
    )
    generate = ActorWorkerCommand(
        session_id="session",
        sequence=2,
        operation="generate",
        remaining_seconds=5,
        request=request,
        parameters=parameters,
    )
    close = ActorWorkerCommand(
        session_id="session", sequence=3, operation="close", remaining_seconds=5
    )
    return configure, generate, close, loader, service


def test_client_preflight_reuse_budget_rejection_and_close(tmp_path: Path) -> None:
    _, loader, request, params, control, service, channel, client = worker_case(
        tmp_path
    )
    client.validate(request, params, control)
    assert loader.loads == 1 and loader.session.calls == 0
    assert client.generate(request, params, control) == loader.session.output
    with pytest.raises(ActorInputBudgetExceeded):
        client.validate(
            request, params.model_copy(update={"max_input_tokens": 1}), control
        )
    assert not service.closed and channel.aborts == 0
    assert client.generate(request, params, control).prompt_tokens == 3
    assert loader.loads == 1 and loader.session.calls == 2
    client.close(control)
    client.close(control)
    assert service.closed and loader.session.closed == 1 and channel.finishes == 1
    parsed = [decode_command(raw) for raw in channel.sent]
    assert [c.sequence for c in parsed] == list(range(1, len(parsed) + 1))
    assert sum(c.operation == "configure" for c in parsed) == 1
    with pytest.raises(OwnershipConflict):
        client.generate(request, params, control)


@pytest.mark.parametrize("fault", ["repeat", "skip", "session", "reconfigure"])
def test_invalid_sequence_cannot_reexecute(tmp_path: Path, fault: str) -> None:
    configure, generate, close, loader, service = commands(tmp_path)
    assert service.handle(configure).status == "ok"
    assert service.handle(generate).status == "ok"
    bad = {
        "repeat": generate,
        "skip": close.model_copy(update={"sequence": 4}),
        "session": close.model_copy(update={"session_id": "other"}),
        "reconfigure": configure.model_copy(update={"sequence": 3}),
    }[fault]
    reply = service.handle(bad)
    assert reply.status == "error" and reply.error is not None
    assert loader.session.calls == 1 and loader.session.closed == 1 and service.closed


@pytest.mark.parametrize(
    "change",
    [
        {"sequence": 0},
        {"sequence": True},
        {"sequence": 10000},
        {"remaining_seconds": 0},
        {"remaining_seconds": float("nan")},
        {"remaining_seconds": True},
        {"artifact": None},
        {"operation": "unknown"},
        {"extra": 1},
    ],
)
def test_invalid_command_contract(tmp_path: Path, change: dict[str, Any]) -> None:
    configure, _, _, loader, _ = commands(tmp_path)
    with pytest.raises(ValidationError):
        ActorWorkerCommand.model_validate({**configure.model_dump(), **change})
    assert loader.loads == 0


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b'{"sequence":1,"sequence":2}', b"null", b"\xff"]
)
def test_malformed_wire_rejected(raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        decode_command(raw)


def test_wire_requires_canonical_and_reply_identity(tmp_path: Path) -> None:
    configure, _, _, _, service = commands(tmp_path)
    raw = configure.model_dump_json().encode()
    assert decode_command(raw) == configure
    with pytest.raises(ValueError):
        decode_command(b" " + raw)
    reply = service.handle(configure)
    assert decode_reply(configure, reply.model_dump_json().encode()) == reply
    for update in (
        {"sequence": 2},
        {"session_id": "other"},
        {"command_sha256": "0" * 64},
    ):
        wrong = reply.model_copy(update=update)
        with pytest.raises(ValueError):
            decode_reply(configure, wrong.model_dump_json().encode())


@pytest.mark.parametrize(
    "field,value",
    [("prompt_tokens", 0), ("completion_tokens", 101), ("finish_reason", "other")],
)
def test_invalid_engine_output_fails_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    _, loader, request, params, control, service, channel, client = worker_case(
        tmp_path
    )
    loader.session.output = loader.session.output.model_copy(update={field: value})
    with pytest.raises(ActorWorkerFailure) as caught:
        client.generate(request, params, control)
    assert (
        caught.value.reply.error is not None and service.closed and channel.aborts == 1
    )
    assert loader.session.calls == 1
    with pytest.raises(OwnershipConflict):
        client.generate(request, params, control)


def test_failure_preserves_original_and_cleanup_without_resend(tmp_path: Path) -> None:
    _, _, request, params, control, _, channel, client = worker_case(tmp_path)
    stopped = OperationStopped("CANCELLED", "parent")
    cleanup = OSError("abort failed")
    channel.failure = stopped
    channel.cleanup_failure = cleanup
    with pytest.raises(BaseExceptionGroup) as caught:
        client.validate(request, params, control)
    assert caught.value.exceptions == (stopped, cleanup)
    assert len(channel.sent) == 1
    with pytest.raises(OwnershipConflict):
        client.generate(request, params, control)


def test_corrupt_reply_and_preflight_mismatch_have_distinct_effects(
    tmp_path: Path,
) -> None:
    _, loader, request, params, control, _, channel, client = worker_case(tmp_path)
    with pytest.raises(ValidationError):
        client.validate(
            request, params.model_copy(update={"enable_thinking": True}), control
        )
    assert not channel.sent and channel.aborts == 0
    channel.broken_reply = b"{}"
    with pytest.raises(ValidationError):
        client.generate(request, params, control)
    assert len(channel.sent) == 1 and channel.aborts == 1 and loader.session.calls == 0


def test_close_unused_client_does_not_configure_or_load(tmp_path: Path) -> None:
    _, loader, _, _, control, _, channel, client = worker_case(tmp_path)
    client.close(control)
    assert not channel.sent and loader.loads == 0 and channel.aborts == 1


def test_stream_full_session_and_bad_tail(tmp_path: Path) -> None:
    configure, generate, close, loader, service = commands(tmp_path)
    output = io.BytesIO()
    serve(
        service,
        io.BytesIO(
            b"".join(
                frame(c.model_dump_json().encode(), MAX_WORKER_PACKET)
                for c in (configure, generate, close)
            )
        ),
        output,
    )
    stream = io.BytesIO(output.getvalue())
    for command in (configure, generate, close):
        size = struct.unpack(">I", stream.read(4))[0]
        assert decode_reply(command, stream.read(size)).status == "ok"
    assert stream.read() == b"" and loader.session.closed == 1


@pytest.mark.parametrize(
    "tail",
    [
        b"\0",
        struct.pack(">I", MAX_WORKER_PACKET + 1),
        struct.pack(">I", 2) + b"{",
        struct.pack(">I", 2) + b"{}",
    ],
)
def test_stream_invalid_input_closes_owned_engine(tmp_path: Path, tail: bytes) -> None:
    configure, generate, _, loader, service = commands(tmp_path)
    stream = io.BytesIO(
        frame(configure.model_dump_json().encode(), MAX_WORKER_PACKET)
        + frame(generate.model_dump_json().encode(), MAX_WORKER_PACKET)
        + tail
    )
    with pytest.raises((EOFError, ValueError)):
        serve(service, stream, io.BytesIO())
    assert loader.session.closed == 1 and service.closed


@pytest.mark.parametrize(
    "change", [{"worker": None}, {"schema_version": "actor-worker-reply/0"}]
)
def test_configuration_reply_requires_current_identity_schema(
    tmp_path: Path, change: dict[str, object]
) -> None:
    configure, _, _, _, service = commands(tmp_path)
    reply = service.handle(configure)
    assert reply.worker is not None
    wrong = reply.model_copy(update=change)
    with pytest.raises(ValidationError):
        decode_reply(configure, wrong.model_dump_json().encode())
