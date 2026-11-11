"""Real file/journal composition, explicitly synthetic admission/termination.

Physical worker termination is tested separately. UnitSessionAuthority never
proves production permission, actual exit, release binding or hard supervision.
"""

from pathlib import Path
from unittest.mock import patch
import pytest
from lab_generate_skill.adapters.storage.observed_inspection import (
    ObservedStorageInspection,
)
from lab_generate_skill.adapters.storage.worker_protocol import decode_command
from lab_generate_skill.adapters.storage.session_resolution import (
    resolve_registered_storage,
)
from lab_generate_skill.adapters.storage.resolution_result import (
    StorageResolutionFailure,
)
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from lab_generate_skill.adapters.storage.worker_protocol import encode_command
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    OperationStopped,
)
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionResolution,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from evidence_session_fixtures import binding, resolution
from registered_exchange_fixtures import harness
from evidence_session_storage_fixtures import snapshot_path


def test_completed_storage_resolution_and_replay_never_repeat_io(
    tmp_path: Path,
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    result = resolve_registered_storage(
        f.raw,
        binding(),
        f.ledger,
        proposed.operation,
        f.controls,
        proposed.worker_end,
        ObservedStorageInspection(decode_command(f.raw)[0]),
    )
    assert result.snapshot is not None
    assert result.snapshot.entries[-1].stage == "resolved"
    assert result.snapshot.entries[-1].outcome == original.outcome
    assert (
        result.observation is not None and result.observation.object_state == "present"
    )
    with patch(
        "lab_generate_skill.adapters.storage.inspection.inspect_exchange_storage",
        side_effect=AssertionError("reinspect"),
    ):
        repeated = resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert repeated.resolution == result.resolution and repeated.observation is None
    assert repeated.snapshot == result.snapshot
    with pytest.raises(InvalidTransition):
        another = resolution(original.intent, 2)
        resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            another.operation,
            f.controls,
            another.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )


def test_unconfirmed_worker_isolates_without_inspecting_storage(tmp_path: Path) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent, ended=False)
    with patch(
        "lab_generate_skill.adapters.storage.inspection.inspect_exchange_storage",
        side_effect=AssertionError("read before exit known"),
    ):
        result = resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            None,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert (
        result.snapshot is not None
        and result.snapshot.entries[-1].stage == "quarantined"
    )
    assert (
        result.resolution.object_state == result.resolution.cleanup_state == "unknown"
    )
    assert result.snapshot.entries[-1].outcome == original.outcome


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_temporary_remains_untouched_and_blocks_reuse(
    tmp_path: Path, kind: str
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    temporary = (
        tmp_path / "evidence" / "blobs" / exchange_temporary_name(f.command.exchange_id)
    )
    if kind == "regular":
        temporary.write_bytes(b"retained")
    else:
        temporary.symlink_to(tmp_path / "absent")
    inode = temporary.lstat().st_ino
    result = resolve_registered_storage(
        f.raw,
        binding(),
        f.ledger,
        proposed.operation,
        f.controls,
        proposed.worker_end,
        ObservedStorageInspection(decode_command(f.raw)[0]),
    )
    assert (
        result.snapshot is not None
        and result.snapshot.entries[-1].stage == "quarantined"
    )
    assert result.resolution.cleanup_state == "failed"
    assert temporary.lstat().st_ino == inode


def test_missing_successful_object_never_becomes_resolved(tmp_path: Path) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    (tmp_path / "evidence" / "blobs" / f.command.reference.sha256).unlink()
    result = resolve_registered_storage(
        f.raw,
        binding(),
        f.ledger,
        proposed.operation,
        f.controls,
        proposed.worker_end,
        ObservedStorageInspection(decode_command(f.raw)[0]),
    )
    assert result.resolution.object_state == "absent"
    assert (
        result.snapshot is not None
        and result.snapshot.entries[-1].stage == "quarantined"
    )


@pytest.mark.parametrize("record_failure", [False, True])
def test_corruption_retains_original_error_and_recording_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_failure: bool
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    blob = tmp_path / "evidence" / "blobs" / f.command.reference.sha256
    blob.write_bytes(b"corrupted")
    if record_failure:

        def fail(*args: object, **kwargs: object) -> EvidenceSessionSnapshot:
            raise OSError("record failed")

        monkeypatch.setattr(f.ledger, "resolve", fail)
    with pytest.raises(StorageResolutionFailure) as caught:
        resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    failure = caught.value
    assert failure.result.resolution.object_state == "unknown"
    assert failure.result.resolution.cleanup_state == "unknown"
    if record_failure:
        assert isinstance(failure.__cause__, BaseExceptionGroup)
        assert len(failure.__cause__.exceptions) == 2
        assert failure.result.snapshot is None
    else:
        assert failure.result.snapshot is not None
        assert failure.result.snapshot.entries[-1].stage == "quarantined"
    assert blob.read_bytes() == b"corrupted"


def test_commit_ack_loss_replays_only_stored_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    commit = f.ledger.resolve

    def lost(
        value: EvidenceSessionBinding, fact: EvidenceSessionResolution, revision: int
    ) -> EvidenceSessionSnapshot:
        commit(value, fact, revision)
        raise OSError("ack lost")

    monkeypatch.setattr(f.ledger, "resolve", lost)
    with pytest.raises(StorageResolutionFailure) as caught:
        resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert caught.value.result.snapshot is None
    with patch(
        "lab_generate_skill.adapters.storage.inspection.inspect_exchange_storage",
        side_effect=AssertionError("new inspection"),
    ):
        repeated = resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert (
        repeated.snapshot is not None
        and repeated.snapshot.entries[-1].stage == "resolved"
    )


@pytest.mark.parametrize("fault", ["command", "worker", "parent", "execute"])
def test_changed_original_identity_refused_before_inspection(
    tmp_path: Path, fault: str
) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    raw, cleanup, ended = f.raw, proposed.operation, proposed.worker_end
    assert ended is not None
    if fault == "command":
        raw = encode_command(
            f.command.model_copy(
                update={"max_object_bytes": f.command.max_object_bytes + 1}
            ),
            b"original",
        )
    elif fault == "worker":
        ended = ended.model_copy(
            update={
                "worker": ended.worker.model_copy(
                    update={"start_ticks": ended.worker.start_ticks + 1}
                )
            }
        )
    elif fault == "parent":
        cleanup = cleanup.model_copy(update={"parent_operation_id": "other"})
    else:
        cleanup = f.op
    with (
        patch(
            "lab_generate_skill.adapters.storage.inspection.inspect_exchange_storage",
            side_effect=AssertionError("inspect"),
        ),
        pytest.raises((OwnershipConflict, ValueError)),
    ):
        resolve_registered_storage(
            raw,
            binding(),
            f.ledger,
            cleanup,
            f.controls,
            ended,
            ObservedStorageInspection(decode_command(raw)[0]),
        )
    assert f.ledger.read(binding(), f.op) == original.snapshot


def test_expired_cleanup_cannot_change_session(tmp_path: Path) -> None:
    f = harness(tmp_path)
    original = f.execute()
    proposed = resolution(original.intent)
    before = snapshot_path(tmp_path / "sessions").read_bytes()
    f.clock.sleep(100)
    with pytest.raises(OperationStopped):
        resolve_registered_storage(
            f.raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(f.raw)[0]),
        )
    assert snapshot_path(tmp_path / "sessions").read_bytes() == before


@pytest.mark.parametrize("raw", [b"", b"bad", b"\0\0\0\x02{}"])
def test_malformed_command_never_reads_or_changes_session(
    tmp_path: Path, raw: bytes
) -> None:
    f = harness(tmp_path)
    proposed = resolution(f.execute().intent)
    before = snapshot_path(tmp_path / "sessions").read_bytes()
    with (
        patch.object(f.ledger, "read", side_effect=AssertionError("read")),
        pytest.raises(ValueError),
    ):
        resolve_registered_storage(
            raw,
            binding(),
            f.ledger,
            proposed.operation,
            f.controls,
            proposed.worker_end,
            ObservedStorageInspection(decode_command(raw)[0]),
        )
    assert snapshot_path(tmp_path / "sessions").read_bytes() == before
