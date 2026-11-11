"""Real journal and data path order; faults retain original pending/returned facts."""

from registered_exchange_fixtures import parent_identity

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.storage import evidence_worker
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.worker_protocol import decode_reply
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from lab_generate_skill.adapters.storage.physical_exchange import (
    PhysicalEvidenceExchange,
)
from lab_generate_skill.adapters.storage.registered_exchange_result import (
    RegisteredExchangeFailure,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    InvalidTransition,
    OperationStopped,
)
from evidence_session_fixtures import binding, intent
from registered_exchange_fixtures import harness


def test_durable_registration_before_real_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = harness(tmp_path)
    physical = evidence_worker.exchange
    calls: list[str] = []

    def observed(raw: bytes) -> bytes:
        saved = f.ledger.read(binding(), f.op)
        assert saved.revision == 1 and saved.entries[0].stage == "pending"
        assert saved.entries[0].intent.command_sha256 == hashlib.sha256(raw).hexdigest()
        assert not (tmp_path / "evidence" / "blobs").exists()
        calls.append("one")
        return physical(raw)

    monkeypatch.setattr(evidence_worker, "exchange", observed)
    result = f.execute()
    assert calls == ["one"] and result.outcome.status == "succeeded"
    assert result.snapshot == f.ledger.read(binding(), f.op)
    assert (
        result.snapshot.entries[0].stage == "returned"
        and not result.snapshot.entries[0].reusable
    )
    assert (
        FileEvidenceStore(tmp_path / "evidence", initialize=False).read(
            f.command.reference
        )
        == b"original"
    )
    assert hashlib.sha256(result.reply).hexdigest() == result.outcome.reply_sha256
    with pytest.raises(RegisteredExchangeFailure) as repeated:
        f.execute()
    assert isinstance(repeated.value.__cause__, DispatchAlreadyCommitted)
    assert calls == ["one"]


def test_worker_failure_remains_failed_result(tmp_path: Path) -> None:
    f = harness(tmp_path, reading=True)
    result = f.execute()
    reply, body = decode_reply(f.command, result.reply)
    assert reply.error is not None and body == b""
    assert result.outcome.status == "failed"
    assert result.snapshot.entries[0].stage == "returned"
    assert not (tmp_path / "evidence" / "blobs").exists()


@pytest.mark.parametrize("mode", ["missing", "lost_ack", "wrong_ack"])
def test_registration_failure_never_enters_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    f = harness(tmp_path, create=mode != "missing")
    original = f.ledger.begin
    if mode != "missing":

        def begin(
            b: EvidenceSessionBinding, i: EvidenceOperationIntent, revision: int
        ) -> EvidenceSessionSnapshot:
            saved = original(b, i, revision)
            if mode == "lost_ack":
                raise OSError("lost registration acknowledgement")
            return saved.model_copy(update={"entries": ()})

        monkeypatch.setattr(f.ledger, "begin", begin)
    with pytest.raises(RegisteredExchangeFailure) as failed:
        f.execute()
    assert failed.value.observation.phase == "registration"
    assert failed.value.observation.reply is None
    assert not (tmp_path / "evidence" / "blobs").exists()
    if mode != "missing":
        assert f.ledger.read(binding(), f.op).entries[0].stage == "pending"


@pytest.mark.parametrize("committed", [False, True])
def test_outcome_failure_retains_reply_and_never_repeats_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    f = harness(tmp_path)
    original = f.ledger.record_outcome

    def fail(
        b: EvidenceSessionBinding,
        o: EvidenceOperationOutcome,
        revision: int,
        op: OperationContext,
    ) -> EvidenceSessionSnapshot:
        if committed:
            original(b, o, revision, op)
        raise OSError("outcome acknowledgement lost")

    monkeypatch.setattr(f.ledger, "record_outcome", fail)
    with pytest.raises(RegisteredExchangeFailure) as failed:
        f.execute()
    observation = failed.value.observation
    assert (
        observation.phase == "outcome"
        and observation.reply is not None
        and observation.outcome is not None
    )
    assert (
        observation.outcome.reply_sha256
        == hashlib.sha256(observation.reply).hexdigest()
    )
    assert (
        FileEvidenceStore(tmp_path / "evidence", initialize=False).read(
            f.command.reference
        )
        == b"original"
    )
    saved = f.ledger.read(binding(), f.op)
    assert saved.entries[0].stage == ("returned" if committed else "pending")
    with pytest.raises(RegisteredExchangeFailure) as retry:
        f.execute()
    assert isinstance(retry.value.__cause__, DispatchAlreadyCommitted)


def test_deadline_after_registration_keeps_pending_without_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = harness(tmp_path)
    original = f.ledger.begin

    def expire(
        b: EvidenceSessionBinding, i: EvidenceOperationIntent, revision: int
    ) -> EvidenceSessionSnapshot:
        saved = original(b, i, revision)
        f.clock.wall += timedelta(seconds=11)
        f.clock.elapsed += 11
        return saved

    monkeypatch.setattr(f.ledger, "begin", expire)
    with pytest.raises(RegisteredExchangeFailure) as failed:
        f.execute()
    assert isinstance(failed.value.__cause__, OperationStopped)
    assert not (tmp_path / "evidence" / "blobs").exists()


def test_stop_after_registration_preserves_original_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = harness(tmp_path)

    def stop(raw: bytes) -> bytes:
        raise KeyboardInterrupt()

    monkeypatch.setattr(evidence_worker, "exchange", stop)
    with pytest.raises(KeyboardInterrupt) as failed:
        f.execute()
    assert getattr(failed.value, "registered_exchange").phase == "exchange"
    assert f.ledger.read(binding(), f.op).entries[0].stage == "pending"
    assert not (tmp_path / "evidence" / "blobs").exists()


@pytest.mark.parametrize("revision", [-1, True, "0", None])
def test_invalid_revision_before_identity_or_storage(
    tmp_path: Path, revision: object
) -> None:
    f = harness(tmp_path)
    with pytest.raises(ValueError):
        f.execute(cast(int, revision))
    assert f.ledger.read(binding(), f.op).revision == 0
    assert not (tmp_path / "evidence" / "blobs").exists()


@pytest.mark.parametrize("raw", [b"", b"broken", b"\0\0\0\1{", b"\0\0\0\0"])
def test_invalid_packet_no_intent(tmp_path: Path, raw: bytes) -> None:
    f = harness(tmp_path)
    with pytest.raises(ValueError):
        registered_exchange(
            raw,
            binding(),
            0,
            f.ledger,
            f.op,
            f.controls,
            PhysicalEvidenceExchange(raw),
            controller=parent_identity(),
        )
    assert f.ledger.read(binding(), f.op).revision == 0
    assert not (tmp_path / "evidence" / "blobs").exists()


def test_successful_read_preserves_original_bytes(tmp_path: Path) -> None:
    from test_filesystem_evidence import metadata

    f = harness(tmp_path, reading=True)
    storage = FileEvidenceStore(tmp_path / "evidence")
    assert storage.put(b"original", metadata()) == f.command.reference
    before = {
        p.name: p.read_bytes() for p in (tmp_path / "evidence" / "blobs").iterdir()
    }
    result = f.execute()
    reply, body = decode_reply(f.command, result.reply)
    assert body == b"original" and reply.error is None
    assert result.outcome.status == "succeeded"
    assert (
        result.intent.kind == "read" and result.snapshot.entries[0].stage == "returned"
    )
    assert {
        p.name: p.read_bytes() for p in (tmp_path / "evidence" / "blobs").iterdir()
    } == before


def test_deadline_after_data_retains_reply_and_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = harness(tmp_path)
    physical = evidence_worker.exchange

    def expire_after_data(raw: bytes) -> bytes:
        reply = physical(raw)
        assert decode_reply(f.command, reply)[0].error is None
        f.clock.wall += timedelta(seconds=11)
        f.clock.elapsed += 11
        return reply

    monkeypatch.setattr(evidence_worker, "exchange", expire_after_data)
    with pytest.raises(RegisteredExchangeFailure) as failed:
        f.execute()
    assert isinstance(failed.value.__cause__, OperationStopped)
    observed = failed.value.observation
    assert (
        observed.phase == "outcome"
        and observed.reply is not None
        and observed.outcome is not None
    )
    assert observed.outcome.status == "succeeded"
    cleanup = f.op.cleanup("inspect-original", now=f.clock.wall, seconds=10)
    saved = f.ledger.read(binding(), cleanup)
    assert saved.entries[0].stage == "pending" and saved.entries[0].outcome is None
    assert (
        FileEvidenceStore(tmp_path / "evidence", initialize=False).read(
            f.command.reference
        )
        == b"original"
    )
