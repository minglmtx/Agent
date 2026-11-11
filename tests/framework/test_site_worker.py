"""Site framing, frozen scope, once-only effects and original failure ownership."""

from datetime import datetime, timezone
import io
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.worker_protocol import (
    SiteWorkerCommand,
    SiteWorkerReply,
    decode_command,
    decode_reply,
    MAX_PACKET,
)
from lab_generate_skill.adapters.sites.worker_stream import read_command, serve
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.adapters.processes.stream_frames import read_frame, write_frame
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from site_worker_fixtures import configuration, operation, case, sources
from test_slurm_commands import guard


def first() -> SiteWorkerCommand:
    config = configuration()
    return SiteWorkerCommand(
        session_id="site-session",
        sequence=1,
        phase="configure",
        operation=operation(config),
        remaining_seconds=30.0,
        controller=current_process_identity(),
        configuration=config,
    )


def test_original_start_close_once_and_no_implicit_release() -> None:
    instance, service, channel, client, authority = case()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    started = client.start(op, control=guard())
    assert started.files == client.configuration.files
    cleanup = op.cleanup("site-close", now=datetime.now(timezone.utc), seconds=30)
    exits = client.close(cleanup, control=guard())
    client.close(cleanup, control=guard())
    assert (
        instance.calls == ["start", "stop"]
        and channel.finishes == 1
        and channel.aborts == 0
    )
    assert len(channel.calls) == 3 and exits and exits[0].state == "reaped"
    assert authority.calls == ["configure", "start", "close", "close"]
    with pytest.raises(InvalidTransition):
        client.start(op, control=guard())


@pytest.mark.parametrize(
    "change",
    [
        "sequence",
        "missing_controller",
        "missing_configuration",
        "old",
        "extra",
        "zero",
        "bool",
        "nan",
        "scope",
    ],
)
def test_command_invalid_before_effect(change: str) -> None:
    value = first().model_dump()
    if change == "sequence":
        value["sequence"] = 2
    elif change == "missing_controller":
        value["controller"] = None
    elif change == "missing_configuration":
        value["configuration"] = None
    elif change == "old":
        value["schema_version"] = "site-worker-command/0"
    elif change == "extra":
        value["callable"] = "anything"
    elif change == "scope":
        value["operation"]["allocation_id"] = "another"
    else:
        value["remaining_seconds"] = {"zero": 0.0, "bool": True, "nan": float("nan")}[
            change
        ]
    with pytest.raises((ValueError, OwnershipConflict)):
        SiteWorkerCommand.model_validate(value)


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"null", b"[]", b'{"x":1,"x":2}', b"\xff", b'{"x":NaN}']
)
def test_invalid_wire(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_command(raw)


def test_canonical_wire_and_exact_command_reply_identity() -> None:
    command = first()
    assert decode_command(command.model_dump_json().encode()) == command
    with pytest.raises(ValueError):
        decode_command(b" " + command.model_dump_json().encode())
    _, service, _, _, _ = case()
    reply = service.handle(command)
    assert command.configuration is not None
    for field, value in [("session_id", "other"), ("command_sha256", "0" * 64)]:
        bad = reply.model_copy(update={field: value})
        with pytest.raises(ValueError):
            decode_reply(command, command.configuration, bad.model_dump_json().encode())
    service.close()


@pytest.mark.parametrize(
    "field,value", [("site_id", "reddit"), ("apptainer", "relative")]
)
def test_configuration_does_not_guess_another_site(field: str, value: str) -> None:
    data = configuration().model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate(data)


@pytest.mark.parametrize(
    "token_field,value",
    [
        ("provider_version", "1"),
        ("resource_kind", "browser"),
        ("expected_resource_id", "another"),
        ("provider_id", "old"),
    ],
)
def test_wrong_allocation_declined(token_field: str, value: str) -> None:
    data = configuration().model_dump()
    data["token"][token_field] = value
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate(data)


@pytest.mark.parametrize("which", ["authority", "guard", "installation"])
def test_no_factory_effect_before_all_admission_checks(which: str) -> None:
    instance, service, channel, client, authority = case()
    error = OwnershipConflict("injected denial")

    def denied(*args: Any) -> Any:
        raise error

    if which == "authority":
        authority.error = error
    elif which == "guard":
        service.guard_verifier = denied
    else:
        service.installation_verifier = denied
    with pytest.raises((OwnershipConflict, SiteWorkerFailure)):
        client.configure(operation(client.configuration), control=guard())
    assert instance.calls == []
    assert not channel.calls if which == "authority" else len(channel.calls) == 1


@pytest.mark.parametrize("kind", ["start", "both", "unconfirmed"])
def test_partial_start_or_stop_errors_retain_facts_without_retry(kind: str) -> None:
    instance, service, channel, client, _ = case()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    if kind in ("start", "both"):
        instance.error = OSError("original startup failure")
        if kind == "both":
            instance.cleanup_error = OSError("original stop failure")
        with pytest.raises(SiteWorkerFailure) as caught:
            client.start(op, control=guard())
    else:
        client.start(op, control=guard())
        instance.unconfirmed = True
        with pytest.raises(SiteWorkerFailure) as caught:
            client.close(
                op.cleanup("close", now=datetime.now(timezone.utc), seconds=30),
                control=guard(),
            )
    assert caught.value.reply.error is not None and client.state == "quarantined"
    count = list(instance.calls)
    service.close()
    assert instance.calls == count
    with pytest.raises(InvalidTransition):
        client.start(op, control=guard())


def test_unknown_wire_and_abort_failure_both_preserved() -> None:
    instance, _, channel, client, _ = case()
    primary = OSError("unknown send")
    cleanup = OSError("abort failure")
    channel.error = primary
    channel.abort_error = cleanup
    with pytest.raises(BaseExceptionGroup) as caught:
        client.configure(operation(client.configuration), control=guard())
    assert caught.value.exceptions == (primary, cleanup) and instance.calls == []
    assert len(channel.calls) == 1 and client.state == "quarantined"


def test_wrong_parent_cleanup_cannot_close_existing_instance() -> None:
    instance, _, channel, client, _ = case()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    client.start(op, control=guard())
    cleanup = op.cleanup(
        "close", now=datetime.now(timezone.utc), seconds=30
    ).model_copy(update={"parent_operation_id": "foreign"})
    with pytest.raises(OwnershipConflict):
        client.close(cleanup, control=guard())
    assert instance.calls == ["start"] and len(channel.calls) == 2
    client.close(
        op.cleanup("correct", now=datetime.now(timezone.utc), seconds=30),
        control=guard(),
    )


@pytest.mark.parametrize(
    "raw", [b"\0", b"\0\0\0\0", b"\xff\xff\xff\xff", b"\0\0\0\x03x"]
)
def test_frame_truncation_and_limit(raw: bytes) -> None:
    with pytest.raises((ValueError, EOFError)):
        read_command(io.BytesIO(raw))


def test_eof_and_broken_output_close_original_site_once() -> None:
    instance, service, _, _, _ = case()
    source = io.BytesIO()
    sink = io.BytesIO()
    serve(service, source, sink, first())
    assert instance.calls == []
    assert read_frame(io.BytesIO(sink.getvalue()), MAX_PACKET)

    class Broken(io.BytesIO):
        def write(self, data: Any) -> int:
            return 0

    instance, service, _, _, _ = case()
    with pytest.raises(BrokenPipeError):
        serve(service, io.BytesIO(), Broken(), first())
    assert instance.calls == []


def test_shared_framing_short_writes_and_multiple_frames() -> None:
    class Short(io.BytesIO):
        def write(self, data: Any) -> int:
            return super().write(data[:1])

    sink = Short()
    write_frame(sink, b"abc", 3)
    write_frame(sink, b"x", 3)
    source = io.BytesIO(sink.getvalue())
    assert read_frame(source, 3) == b"abc"
    assert read_frame(source, 3) == b"x"
    assert read_frame(source, 3) is None


def test_partial_stop_facts_survive_error_reply() -> None:
    from lab_generate_skill.domain.native_services import NativeServiceExit

    instance, _, _, client, _ = case()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    client.start(op, control=guard())
    exits = (
        NativeServiceExit(
            service="unit",
            process_id=1,
            returncode=None,
            state="unconfirmed",
            kill_requested=True,
        ),
    )
    error = OSError("partial stop failed")
    setattr(error, "service_exits", exits)
    instance.cleanup_error = error
    with pytest.raises(SiteWorkerFailure) as caught:
        client.close(
            op.cleanup("close", now=datetime.now(timezone.utc), seconds=30),
            control=guard(),
        )
    assert caught.value.reply.exits == exits and caught.value.reply.error is not None
    assert instance.calls == ["start", "stop"]


def test_final_cancel_retains_actual_start_reply_and_never_resends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, _, channel, client, _ = case()

    class Control:
        cancelled = False

        def checkpoint(self) -> float:
            if self.cancelled:
                raise TimeoutError("after actual site return")
            return 30.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = Control()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    original = channel.exchange

    def exchange(payload: bytes, guard: Any) -> bytes:
        result = original(payload, guard)
        control.cancelled = True
        return result

    monkeypatch.setattr(channel, "exchange", exchange)
    with pytest.raises(TimeoutError):
        client.start(op, control=control)
    assert client.last_reply is not None and client.last_reply.started is not None
    assert (
        client.state == "quarantined"
        and len(channel.calls) == 2
        and instance.calls == ["start", "stop"]
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://evil.example:12001/admin",
        "http://127.0.0.1:12002/admin",
        "http://user@127.0.0.1:12001/admin",
        "https://127.0.0.1:12001/admin",
        "http://127.0.0.1:12001/admin#x",
    ],
)
def test_endpoint_cannot_escape_original_loopback_port(endpoint: str) -> None:
    with pytest.raises(ValueError):
        SiteInstanceStarted(
            files=configuration().files, endpoint=endpoint, ports=(12001, 12002)
        )


def test_site_step_is_batch_cpu_and_fixes_provider() -> None:
    from lab_generate_skill.adapters.slurm.step_launch import (
        fixed_site_step_argv,
        site_step_name,
    )
    from slurm_step_fixtures import target

    t = target()
    config = configuration(job_id=t.execution.job_id)
    argv = fixed_site_step_argv(
        config.token,
        t.execution,
        t.launcher.node_id,
        python_executable="/trusted/python",
        srun_executable="/usr/bin/srun",
    )
    assert (
        "--gres=none" in argv and "--job-name=" + site_step_name(config.token) in argv
    )
    assert argv[-1] == "lab_generate_skill.bootstrap.site_worker"
    with pytest.raises(ValueError):
        fixed_site_step_argv(
            config.token.model_copy(update={"provider_id": "old"}),
            t.execution,
            t.launcher.node_id,
            python_executable="/trusted/python",
            srun_executable="/usr/bin/srun",
        )


@pytest.mark.parametrize("broken", ["write", "flush"])
def test_instance_cleanup_survives_diagnostic_pipe_failure(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    from unittest.mock import Mock
    import sys
    from lab_generate_skill.sites.shopping_admin.instance import AdminInstance
    from lab_generate_skill.sites.shopping_admin.worker_instance import (
        AdminWorkerInstance,
    )
    from lab_generate_skill.adapters.processes.deadline import DeadlineControl

    class Broken:
        def write(self, value: str) -> int:
            if broken == "write":
                raise BrokenPipeError("diagnostic pipe closed")
            return len(value)

        def flush(self) -> None:
            if broken == "flush":
                raise OSError("diagnostic flush failed")

    instance = Mock(spec=AdminInstance)
    instance.stop.return_value = ()
    worker = AdminWorkerInstance(instance)
    control = DeadlineControl(2, "test-stop")
    with monkeypatch.context() as scope:
        scope.setattr(sys, "stderr", Broken())
        assert worker.stop(control) == ()
    instance.stop.assert_called_once_with(control)
