"""Early identity is available before factory/effects and survives startup failure."""

from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.worker_protocol import (
    SiteWorkerCommand,
    decode_command,
)
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from site_worker_fixtures import case, operation
from test_site_worker import first
from test_slurm_commands import guard


def test_configure_close_creates_no_instance() -> None:
    instance, service, channel, client, authority = case()
    op = operation(client.configuration)
    ready = client.configure(op, control=guard())
    assert ready.owner_guard.controller == client.controller
    assert service.instance is None and instance.calls == []
    assert client.prepared == ready and client.state == "configured"
    with pytest.raises(InvalidTransition):
        client.configure(op, control=guard())
    assert (
        client.close(
            op.cleanup("close", now=datetime.now(timezone.utc), seconds=10),
            control=guard(),
        )
        == ()
    )
    assert instance.calls == [] and channel.finishes == 1
    assert authority.calls == ["configure", "close"]


def test_start_without_handshake_has_no_wire_effect() -> None:
    instance, service, channel, client, _ = case()
    with pytest.raises(InvalidTransition):
        client.start(operation(client.configuration), control=guard())
    assert not channel.calls and not instance.calls and service.instance is None


@pytest.mark.parametrize(
    "field", ["deadline", "operation_id", "allocation_id", "recovery_ref"]
)
def test_start_cannot_change_configured_operation(field: str) -> None:
    instance, service, channel, client, _ = case()
    op = operation(client.configuration)
    client.configure(op, control=guard())
    change: dict[str, Any] = {field: "foreign"}
    if field == "deadline":
        change[field] = op.deadline + timedelta(seconds=1)
    elif field == "recovery_ref":
        change[field] = None
    with pytest.raises(OwnershipConflict):
        client.start(op.model_copy(update=change), control=guard())
    assert len(channel.calls) == 1 and service.instance is None and instance.calls == []


@pytest.mark.parametrize("change", ["session", "operation", "guard"])
def test_worker_checks_original_handshake_before_factory(change: str) -> None:
    instance, service, _, _, _ = case()
    configure = first()
    ready = service.handle(configure)
    assert ready.owner_guard is not None and service.instance is None
    op = configure.operation
    session = configure.session_id
    if change == "session":
        session = "foreign"
    elif change == "operation":
        op = op.model_copy(update={"operation_id": "foreign"})
    else:

        def denied(*args: Any) -> Any:
            raise OwnershipConflict("original guard lost")

        service.guard_verifier = denied
    reply = service.handle(
        SiteWorkerCommand(
            session_id=session,
            sequence=2,
            phase="start",
            operation=op,
            remaining_seconds=5.0,
        )
    )
    assert reply.error is not None and service.instance is None and instance.calls == []


def test_failed_start_retains_early_original_identity() -> None:
    instance, _, _, client, _ = case()
    op = operation(client.configuration)
    ready = client.configure(op, control=guard())
    instance.error = OSError("partial preparation failed")
    with pytest.raises(SiteWorkerFailure):
        client.start(op, control=guard())
    assert client.prepared == ready and client.state == "quarantined"
    assert instance.calls == ["start", "stop"]


def test_old_wire_and_provider_are_rejected() -> None:
    old = first().model_dump()
    old["schema_version"] = "site-worker-command/1"
    with pytest.raises(ValueError):
        SiteWorkerCommand.model_validate(old)
    old_wire = (
        first()
        .model_dump_json()
        .replace("site-worker-configuration/6", "site-worker-configuration/5")
    )
    with pytest.raises(ValueError):
        decode_command(old_wire.encode())


def test_cancel_after_configure_preserves_original_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, service, channel, client, _ = case()

    class Control:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise TimeoutError("after original identity returned")
            return 5.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = Control()
    exchange = channel.exchange

    def stop_after_reply(payload: bytes, original: Any) -> bytes:
        raw = exchange(payload, original)
        control.stopped = True
        return raw

    monkeypatch.setattr(channel, "exchange", stop_after_reply)
    with pytest.raises(TimeoutError):
        client.configure(operation(client.configuration), control=control)
    assert (
        client.prepared is not None
        and client.prepared.owner_guard.controller == client.controller
    )
    assert client.state == "quarantined" and service.instance is None
    assert instance.calls == [] and len(channel.calls) == 1
