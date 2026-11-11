"""Contract/service/client failures without browser startup or real permission."""

from datetime import datetime, timezone
import io
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.adapters.browsergym.worker_protocol import (
    BrowserWorkerCommand,
    decode_command,
    decode_reply,
    MAX_COMMANDS,
)
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.adapters.browsergym.worker_stream import read_command
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from browser_worker_fixtures import case, configuration, action
from browsergym_fixtures import operation
from test_slurm_commands import guard


def first() -> BrowserWorkerCommand:
    config = configuration()
    return BrowserWorkerCommand(
        session_id="session",
        sequence=1,
        phase="configure",
        operation=operation(config.spec, "start"),
        remaining_seconds=30.0,
        controller=current_process_identity(),
        configuration=config,
    )


def test_ordered_start_step_close_without_relaunch() -> None:
    engine, service, channel, client = case()
    op = operation(client.spec, "start")
    started = client.start(op, control=guard(30))
    assert started.observation.sequence == 0
    returned = client.step(action(), operation(client.spec, "step"), control=guard(30))
    assert returned.action == action()
    cleanup = op.cleanup("close", now=datetime.now(timezone.utc), seconds=30)
    client.close(cleanup, control=guard(30))
    client.close(cleanup, control=guard(30))
    assert (
        engine.calls == ["start", "step", "close"]
        and channel.finishes == 1
        and channel.aborts == 0
        and len(channel.calls) == 4
    )
    with pytest.raises(InvalidTransition):
        client.start(op, control=guard(30))


@pytest.mark.parametrize(
    "change",
    [
        "sequence",
        "missing_controller",
        "missing_configuration",
        "action_on_start",
        "cleanup_start",
        "extra",
        "old_version",
        "nan",
        "zero",
        "bool",
    ],
)
def test_invalid_command_shape_no_effect(change: str) -> None:
    data = first().model_dump()
    if change == "sequence":
        data["sequence"] = 2
    elif change == "missing_controller":
        data["controller"] = None
    elif change == "missing_configuration":
        data["configuration"] = None
    elif change == "action_on_start":
        data["action"] = action()
    elif change == "cleanup_start":
        data["operation"]["mode"] = "cleanup"
    elif change == "extra":
        data["extra"] = True
    elif change == "old_version":
        data["schema_version"] = "browser-worker-command/0"
    else:
        data["remaining_seconds"] = {"nan": float("nan"), "zero": 0.0, "bool": True}[
            change
        ]
    with pytest.raises(ValidationError):
        BrowserWorkerCommand.model_validate(data)


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"null", b"[]", b'{"x":1,"x":2}', b"\x00", b'{"x":NaN}']
)
def test_invalid_wire(raw: bytes) -> None:
    with pytest.raises((ValueError, ValidationError)):
        decode_command(raw)


def test_canonical_command_and_close_reserve() -> None:
    command = first()
    assert decode_command(command.model_dump_json().encode()) == command
    with pytest.raises(ValueError):
        decode_command(b" " + command.model_dump_json().encode())
    op = (
        operation(command.configuration.spec, "last")
        if command.configuration
        else command.operation
    )
    with pytest.raises(ValidationError):
        BrowserWorkerCommand(
            session_id="session",
            sequence=MAX_COMMANDS,
            phase="step",
            operation=op,
            remaining_seconds=1.0,
            action=action(),
        )
    closed = BrowserWorkerCommand(
        session_id="session",
        sequence=MAX_COMMANDS,
        phase="close",
        operation=op.cleanup("last-close", now=datetime.now(timezone.utc), seconds=10),
        remaining_seconds=1.0,
    )
    assert closed.phase == "close"


@pytest.mark.parametrize(
    "value",
    [
        "relative",
        "/tmp/../assets",
        "/tmp//assets",
        "/tmp/assets:foreign",
        "/tmp/asset\0bad",
    ],
)
def test_asset_paths_rejected(value: str) -> None:
    data = configuration().model_dump()
    data["library_directories"] = (value,)
    with pytest.raises(ValidationError):
        BrowserWorkerConfiguration.model_validate(data)


@pytest.mark.parametrize("fault", ["repeat", "skip", "session", "scope"])
def test_sequence_or_scope_failure_closes_original_without_new_step(fault: str) -> None:
    engine, service, channel, client = case()
    client.start(operation(client.spec, "start"), control=guard(30))
    command = BrowserWorkerCommand(
        session_id=client.session_id,
        sequence=3,
        phase="step",
        operation=operation(client.spec, "step"),
        remaining_seconds=30.0,
        action=action(),
    )
    if fault == "repeat":
        command = decode_command(channel.calls[0])
    elif fault == "skip":
        command = command.model_copy(update={"sequence": 4})
    elif fault == "session":
        command = command.model_copy(update={"session_id": "other"})
    else:
        command = command.model_copy(
            update={
                "operation": command.operation.model_copy(update={"owner_id": "other"})
            }
        )
    reply = service.handle(command)
    assert (
        reply.error is not None
        and engine.calls == ["start", "close"]
        and service.closed
    )


@pytest.mark.parametrize("dual", [False, True])
def test_actual_return_and_primary_cleanup_errors_survive(dual: bool) -> None:
    engine, service, channel, client = case()
    client.start(operation(client.spec, "start"), control=guard(30))
    engine.failure = OSError("native after return")
    if dual:
        engine.close_failure = RuntimeError("close failed")
    with pytest.raises(BrowserWorkerFailure) as caught:
        client.step(action(), operation(client.spec, "step"), control=guard(30))
    assert caught.value.reply.readout == engine.last_readout == client.last_readout
    assert caught.value.reply.error is not None
    assert caught.value.reply.error.type_name == (
        "ExceptionGroup" if dual else "OSError"
    )
    assert channel.aborts == 1 and client.state == "quarantined"
    with pytest.raises(InvalidTransition):
        client.step(action(), operation(client.spec, "next"), control=guard(30))
    assert len(channel.calls) == 3


@pytest.mark.parametrize("dual", [False, True])
def test_bad_reply_and_abort_failure_never_retry(dual: bool) -> None:
    engine, service, channel, client = case()
    channel.bad_reply = b"{}"
    if dual:
        channel.abort_failure = OSError("abort")
    with pytest.raises((ValueError, BaseExceptionGroup)) as caught:
        client.start(operation(client.spec, "start"), control=guard(30))
    assert getattr(caught.value, "command_capture") == channel.capture
    assert channel.aborts == 1 and client.state == "quarantined"
    with pytest.raises(InvalidTransition):
        client.start(operation(client.spec, "retry"), control=guard(30))
    assert len(channel.calls) == 1


@pytest.mark.parametrize(
    "raw", [b"\0", b"\0\0\0\0", b"\x7f\xff\xff\xff", b"\0\0\0\x04{}"]
)
def test_truncated_or_oversized_stream(raw: bytes) -> None:
    with pytest.raises((ValueError, EOFError)):
        read_command(io.BytesIO(raw))


def test_start_denied_before_any_transport() -> None:
    engine, service, channel, client = case()
    client.authority.denied = True  # type: ignore[attr-defined]
    with pytest.raises(OwnershipConflict):
        client.start(operation(client.spec, "start"), control=guard(30))
    assert not channel.calls and not engine.calls


@pytest.mark.parametrize("kind", ["unconfirmed", "cleanup_error"])
def test_abort_must_confirm_original_channel_close(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.processes.capture import ProcessTermination
    from lab_generate_skill.ports.lifecycle import OperationControl

    engine, service, channel, client = case()
    client.state = "quarantined"
    client.transport_failed = True

    def abort(control: OperationControl) -> ProcessTermination:
        if kind == "unconfirmed":
            return ProcessTermination(123, "unconfirmed", None, True)
        return ProcessTermination(123, "reaped", -9, True, ("pipe close failed",))

    monkeypatch.setattr(channel, "abort", abort)
    close = operation(client.spec, "start").cleanup(
        "close", now=datetime.now(timezone.utc), seconds=10
    )
    with pytest.raises(OwnershipConflict):
        client.close(close, control=guard(10))
    assert getattr(client, "state") == "quarantined"


def test_foreign_observation_sequence_retains_reply_but_no_second_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lab_generate_skill.domain.browser import BrowserAction
    from lab_generate_skill.domain.browser_session import BrowserReadout
    from lab_generate_skill.domain.lifecycle import OperationContext
    from lab_generate_skill.ports.lifecycle import OperationControl

    engine, service, channel, client = case()
    before = client.start(operation(client.spec, "start"), control=guard(30))

    def step(
        action: BrowserAction, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        value = engine.value(operation, action)
        return value.model_copy(
            update={"observation": value.observation.model_copy(update={"sequence": 9})}
        )

    monkeypatch.setattr(engine, "step", step)
    with pytest.raises(OwnershipConflict):
        client.step(action(), operation(client.spec, "step"), control=guard(30))
    assert client.last_readout == before and client.last_reply is not None
    assert (
        client.last_reply.readout is not None
        and client.last_reply.readout.observation.sequence == 9
    )
    assert channel.aborts == 1 and len(channel.calls) == 3


def test_configuration_has_one_public_definition_and_unchanged_wire() -> None:
    from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
    from lab_generate_skill.adapters.browsergym import worker_protocol

    command = first()
    assert isinstance(command.configuration, BrowserWorkerConfiguration)
    assert (
        BrowserWorkerConfiguration.__module__
        == "lab_generate_skill.domain.browser_worker"
    )
    assert getattr(worker_protocol, "BrowserWorkerConfiguration", None) is None
    decoded = decode_command(command.model_dump_json().encode())
    assert decoded == command and decoded.configuration is not None
    assert (
        decoded.configuration.model_dump_json()
        == command.configuration.model_dump_json()
    )


def test_configuration_has_no_native_effects_and_can_close_before_initialization() -> (
    None
):
    from lab_generate_skill.adapters.browsergym.worker_protocol import (
        BrowserWorkerCommand,
    )

    engine, service, channel, client = case()
    configured = first()
    reply = service.handle(configured)
    assert reply.error is None and reply.readout is None
    assert reply.owner_guard is not None and reply.installed_sources is not None
    assert service.engine is None and not engine.calls
    closed = service.handle(
        BrowserWorkerCommand(
            session_id=configured.session_id,
            sequence=2,
            phase="close",
            operation=configured.operation.cleanup(
                "close-before-native", now=datetime.now(timezone.utc), seconds=10
            ),
            remaining_seconds=10.0,
        )
    )
    assert closed.error is None and service.closed and not engine.calls


def test_configuration_observer_failure_prevents_native_start_and_retry() -> None:
    engine, service, channel, client = case()
    primary = OSError("prepared evidence unavailable")

    def observe(*args: object) -> None:
        assert service.engine is None and not engine.calls
        raise primary

    client.configure_observer = observe
    op = operation(client.spec, "start")
    with pytest.raises(OSError) as caught:
        client.start(op, control=guard(30))
    assert caught.value is primary and client.configuration_reply is not None
    assert len(channel.calls) == 1 and client.last_readout is None
    with pytest.raises(InvalidTransition):
        client.start(op, control=guard(30))
    client.close(
        op.cleanup("close", now=datetime.now(timezone.utc), seconds=10),
        control=guard(10),
    )
    assert service.closed and not engine.calls


@pytest.mark.parametrize(
    "version", ["browser-worker-command/1", "browser-worker-command/2"]
)
def test_old_configuration_wire_has_no_implicit_upgrade(version: str) -> None:
    data = first().model_dump()
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        BrowserWorkerCommand.model_validate(data)
