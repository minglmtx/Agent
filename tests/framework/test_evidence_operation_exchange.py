"""Opaque caller control -> private operation -> real registered CAS exchange.

Scope admission remains explicitly synthetic here. These tests exercise current
runtime/session/worker implementations, not the final supervised entry.
"""

from registered_exchange_fixtures import parent_identity

from pathlib import Path
import os
import pytest
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from lab_generate_skill.adapters.storage.physical_exchange import (
    PhysicalEvidenceExchange,
)
from lab_generate_skill.adapters.storage.registered_exchange_result import (
    RegisteredExchangeFailure,
)
from lab_generate_skill.adapters.storage.worker_protocol import (
    encode_command,
    decode_reply,
)
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.runtime.evidence_operations import EvidenceOperations
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_session_fixtures import binding, capacity
from evidence_session_storage_fixtures import UnitSessionAuthority
from evidence_worker_fixtures import command
from test_evidence_operations import OpaqueControl
from test_lifecycle import ManualClock, CancelSwitch


@pytest.mark.parametrize("scope", ["run", "source"])
@pytest.mark.parametrize("stop_after_write", [False, True])
def test_original_control_reaches_actual_registration_and_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str, stop_after_write: bool
) -> None:
    b = EvidenceSessionBinding.model_validate(
        {
            **binding().model_dump(),
            "scope": scope,
            "source_task_id": None if scope == "run" else "source-1",
        }
    )
    sessions, evidence = tmp_path / "sessions", tmp_path / "evidence"
    sessions.mkdir()
    evidence.mkdir()
    clock = ManualClock()
    caller = OpaqueControl(clock)
    request = command(evidence)
    packet = encode_command(request, b"evidence")
    prepared = EvidenceOperations(b, clock, max_io_seconds=5).prepare(
        request.exchange_id, caller
    )
    ledger = FileEvidenceSessions(
        sessions,
        b.storage_id,
        b.storage_config_sha256,
        prepared,
        UnitSessionAuthority(),
    )
    ledger.create(b, capacity(), prepared.operation)
    if stop_after_write:
        link = os.link

        def linked(
            src: str,
            dst: str,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            link(
                src,
                dst,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            caller.stopped = True

        monkeypatch.setattr(os, "link", linked)
        with pytest.raises(RegisteredExchangeFailure) as caught:
            registered_exchange(
                packet,
                b,
                0,
                ledger,
                prepared.operation,
                prepared,
                PhysicalEvidenceExchange(packet),
                controller=parent_identity(),
            )
        assert isinstance(caught.value.__cause__, OperationStopped)
        assert caught.value.observation.reply is not None
        assert decode_reply(request, caught.value.observation.reply)[0].error is None
    else:
        result = registered_exchange(
            packet,
            b,
            0,
            ledger,
            prepared.operation,
            prepared,
            PhysicalEvidenceExchange(packet),
            controller=parent_identity(),
        )
        assert result.outcome.status == "succeeded"
        assert result.intent.operation == prepared.operation
    cleanup = prepared.operation.cleanup(
        "inspect-original", now=clock.utcnow(), seconds=5
    )
    reader = FileEvidenceSessions(
        sessions,
        b.storage_id,
        b.storage_config_sha256,
        OperationGuards(clock, CancelSwitch()),
        UnitSessionAuthority(),
    )
    saved = reader.read(b, cleanup)
    assert saved.entries[0].stage == ("pending" if stop_after_write else "returned")
    assert saved.entries[0].intent.operation == prepared.operation
    assert saved.binding.scope == scope
    assert (evidence / "blobs" / request.reference.sha256).read_bytes() == b"evidence"
