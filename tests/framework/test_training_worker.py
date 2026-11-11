"""Finite role wire and once-only transport tests; explicit synthetic backend."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.training.worker_protocol import (
    TrainingWorkerCommand,
    decode_command,
    decode_reply,
)
from lab_generate_skill.adapters.training.worker_client import TrainingWorkerFailure
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from training_entry_fixtures import TrainingCase, training_case as training_case
from training_worker_fixtures import worker_case, unit_client, train_command
from test_slurm_commands import guard


@pytest.mark.parametrize("value", [None, "", "a" * 64, False, 1, {}])
def test_train_requires_frozen_command_not_legacy_digest_or_empty_input(
    training_case: TrainingCase, tmp_path: Path, value: object
) -> None:
    from typing import Any, cast

    c = worker_case(training_case, tmp_path / "frozen-only")
    backend, _, channel, client = unit_client(c)
    client.configure(guard())
    with pytest.raises((ValueError, ValidationError)):
        client.train(cast(Any, value), guard())
    assert backend.calls == 0 and len(channel.sent) == 1
    client.close(guard())


def test_frozen_wire_cannot_renew_expired_original_training_deadline(
    training_case: TrainingCase, tmp_path: Path
) -> None:
    from datetime import datetime, timezone, timedelta

    c = worker_case(training_case, tmp_path / "expired-frozen")
    backend, service, channel, client = unit_client(c)
    client.configure(guard())
    service.original_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(TrainingWorkerFailure):
        client.train(train_command(c, client, seconds=86400), guard())
    assert backend.calls == 0 and len(channel.sent) == 2 and service.closed


def test_finite_configuration_train_and_close_uses_exact_same_bytes(
    training_case: TrainingCase, tmp_path: Path
) -> None:
    c = worker_case(training_case, tmp_path / "unit-wire")
    backend, service, channel, client = unit_client(c)
    reply = client.configure(guard())
    assert (
        reply.guard is not None and reply.guard.controller == current_process_identity()
    )
    assert backend.calls == backend.closes == 0
    assert client.train(train_command(c, client), guard()) == backend.reference
    with pytest.raises(OwnershipConflict, match="once-only"):
        client.train(train_command(c, client), guard())
    ended = client.close(guard())
    assert client.close(guard()) == ended and ended.returncode == 0
    assert service.closed and backend.calls == backend.closes == 1
    assert len(channel.sent) == 3
    assert tuple(e.command for e in client.exchanges) == tuple(channel.sent)
    assert [e.decoded.operation for e in client.exchanges] == [
        "configure",
        "train",
        "close",
    ]


@pytest.mark.parametrize(
    "fault", ["timeout", "cancel", "partial", "lost-reply", "cleanup"]
)
def test_failure_or_unknown_never_sends_training_again(
    training_case: TrainingCase, tmp_path: Path, fault: str
) -> None:
    c = worker_case(training_case, tmp_path / fault)
    backend, service, channel, client = unit_client(c)
    client.configure(guard())
    if fault == "lost-reply":
        channel.lose_reply = True
    else:
        backend.error = (
            TimeoutError("unit timeout")
            if fault == "timeout"
            else (
                InterruptedError("unit cancellation")
                if fault == "cancel"
                else OSError("unit partial native output")
            )
        )
    if fault == "cleanup":
        backend.cleanup = OSError("unit child close failure")
        channel.abort_error = OSError("unit transport cleanup failure")
    with pytest.raises(
        (TimeoutError, TrainingWorkerFailure, BaseExceptionGroup)
    ) as error:
        client.train(train_command(c, client), guard())
    assert "unit" in str(error.value).lower() or isinstance(
        error.value, (TrainingWorkerFailure, BaseExceptionGroup)
    )
    assert backend.calls == 1 and channel.aborts == 1 and service.closed
    with pytest.raises(OwnershipConflict, match="once-only"):
        client.train(train_command(c, client), guard())
    assert len(channel.sent) == 2 and client.state == "failed"
    assert client.last_command == channel.sent[-1]
    assert getattr(error.value, "training_worker_command") == channel.sent[-1]
    assert decode_command(client.last_command).operation == "train"
    if fault == "cleanup":
        assert isinstance(error.value, BaseExceptionGroup)
        assert isinstance(error.value.exceptions[0], TrainingWorkerFailure)
        assert error.value.exceptions[0].exchange.decoded.error is not None


@pytest.mark.parametrize("fault", ["duplicate", "session", "skip"])
def test_worker_rejects_duplicate_foreign_or_skipped_sequence(
    training_case: TrainingCase, tmp_path: Path, fault: str
) -> None:
    c = worker_case(training_case, tmp_path / fault)
    backend, service, _, client = unit_client(c)
    client.configure(guard())
    if fault == "duplicate":
        command = decode_command(client.exchanges[0].command)
    else:
        command = TrainingWorkerCommand(
            session_id="other" if fault == "session" else client.session_id,
            sequence=2 if fault == "session" else 3,
            operation="train" if fault == "session" else "close",
            contract_sha256=c.digest if fault == "session" else None,
            remaining_seconds=5,
        )
    reply = service.handle(command)
    assert reply.status == "error" and reply.error is not None and service.closed
    assert backend.calls == 0 and backend.closes == 1


@pytest.mark.parametrize(
    "value",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b'{"sequence":true}',
        b'{"schema_version":"sft-worker-command/0"}',
    ],
)
def test_invalid_or_empty_wire_has_no_backend(value: bytes) -> None:
    with pytest.raises((ValueError, ValidationError)):
        decode_command(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", True),
        ("remaining_seconds", "5"),
        ("operation", "generate"),
        ("configuration", None),
        ("unused", 1),
    ],
)
def test_wrong_type_and_silent_extra_fields_rejected_before_effects(
    training_case: TrainingCase, tmp_path: Path, field: str, value: object
) -> None:
    c = worker_case(training_case, tmp_path / (field + "-shape"))
    _, _, _, client = unit_client(c)
    client.configure(guard())
    raw = json.loads(client.exchanges[0].command)
    raw[field] = value
    with pytest.raises((ValueError, ValidationError)):
        decode_command(json.dumps(raw).encode())


def test_noncanonical_and_foreign_reply_are_rejected(
    training_case: TrainingCase, tmp_path: Path
) -> None:
    c = worker_case(training_case, tmp_path / "binding")
    _, _, _, client = unit_client(c)
    client.configure(guard())
    e = client.exchanges[0]
    command = decode_command(e.command)
    with pytest.raises(ValueError, match="canonical"):
        decode_command(e.command + b" ")
    altered = json.loads(e.reply)
    altered["command_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="identity"):
        decode_reply(command, json.dumps(altered).encode())


@pytest.mark.parametrize(
    "fault",
    ["owner", "provider", "release", "installation-ref", "evidence-overlap", "outside"],
)
def test_config_rejects_cross_role_or_changed_original_scope(
    training_case: TrainingCase, tmp_path: Path, fault: str
) -> None:
    from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration

    c = worker_case(training_case, tmp_path / fault)
    raw = c.configuration.model_dump()
    if fault == "owner":
        raw["token"]["owner"]["owner_id"] = "other"
    elif fault == "provider":
        raw["token"]["resource_kind"] = "generator"
    elif fault == "release":
        raw["output"]["training"]["training_release_ref"] = raw["token"]["recovery_ref"]
    elif fault == "installation-ref":
        raw["installation_ref"]["sha256"] = "0" * 64
    else:
        raw["evidence_root"] = (
            c.configuration.output.output_root
            if fault == "evidence-overlap"
            else "/unrelated"
        )
    with pytest.raises(ValueError):
        TrainingWorkerConfiguration.model_validate(raw)
