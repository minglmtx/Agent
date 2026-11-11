"""Actual original exit -> independent fixed resolver -> next I/O; engineering scope."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
    RegisteredStorageFailure,
)
from lab_generate_skill.adapters.storage.resolver_transport import (
    StorageResolverTransport,
    StorageResolverFailure,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    StorageResolutionCommand,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageCommand,
)
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from registered_storage_fixtures import request, ExplicitAdmission, roots
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def setup_exchange(
    root: Path, python: InstalledFixture, *, reading: bool = False
) -> tuple[RegisteredStorageCommand, StorageResolutionCommand]:
    roots(root)
    create = request(root, create=True, installation=python)
    RegisteredStorageTransport(
        str(python.executable), ExplicitAdmission(create)
    ).execute(create, b"", guard(60))
    cmd = request(root, reading=reading, installation=python)
    transport = RegisteredStorageTransport(
        str(python.executable), ExplicitAdmission(cmd)
    )
    try:
        completed = transport.execute(cmd, b"" if reading else b"evidence", guard(60))
        ending = completed.ending
    except RegisteredStorageFailure as error:
        if not reading:
            raise
        assert error.result is not None and error.result.reply.outcome is not None
        assert error.result.reply.outcome.status == "failed"
        ending = error.ending
    assert ending is not None
    cleanup = cmd.operation.cleanup(
        "close-original", now=datetime.now(timezone.utc), seconds=60
    )
    return cmd, StorageResolutionCommand(original=cmd, cleanup=cleanup, ending=ending)


@pytest.mark.parametrize("reading", [False, True])
def test_actual_ending_and_inspection_allow_next_exchange(
    tmp_path: Path, installed_sources: InstalledFixture, reading: bool
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources, reading=reading)
    payload = b"" if reading else b"evidence"
    resolved = StorageResolverTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    ).execute(close, payload, guard(60))
    snapshot = resolved.result.snapshot
    assert (
        snapshot is not None
        and snapshot.revision == 3
        and snapshot.entries[-1].reusable
    )
    end = snapshot.entries[-1].resolutions[-1].worker_end
    assert close.ending is not None
    assert end is not None and end.worker.process_id == close.ending.process_id
    assert resolved.result.reply.worker.process_id != end.worker.process_id
    assert resolved.result.reply.resolution is not None
    assert resolved.result.reply.resolution.object_state == (
        "absent" if reading else "present"
    )
    assert cmd.io is not None
    next_io = cmd.io.model_copy(update={"exchange_id": "next-exchange"})
    next_cmd = cmd.model_copy(
        update={
            "expected_revision": snapshot.revision,
            "io": next_io,
            "operation": cmd.operation.model_copy(update={"operation_id": "next-io"}),
        }
    )
    if reading:
        with pytest.raises(RegisteredStorageFailure) as failed:
            RegisteredStorageTransport(
                str(installed_sources.executable), ExplicitAdmission(next_cmd)
            ).execute(next_cmd, b"", guard(60))
        assert (
            failed.value.result is not None and failed.value.result.snapshot is not None
        )
        assert len(failed.value.result.snapshot.entries) == 2
    else:
        new = RegisteredStorageTransport(
            str(installed_sources.executable), ExplicitAdmission(next_cmd)
        ).execute(next_cmd, payload, guard(60))
        assert new.result.snapshot is not None and len(new.result.snapshot.entries) == 2


def test_unknown_ending_skips_broken_data_root_and_records_isolation(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources)
    (tmp_path / "data").rename(tmp_path / "original-data")
    close = close.model_copy(update={"ending": None})
    done = StorageResolverTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    ).execute(close, b"evidence", guard(60))
    assert (
        done.result.snapshot is not None
        and not done.result.snapshot.entries[-1].reusable
    )
    resolution = done.result.reply.resolution
    assert resolution is not None and resolution.worker_end is None
    assert resolution.object_state == resolution.cleanup_state == "unknown"
    assert not (tmp_path / "data").exists()


def test_remaining_temporary_stays_untouched_and_quarantined(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources)
    assert cmd.io is not None
    temporary = (
        tmp_path / "data" / "blobs" / exchange_temporary_name(cmd.io.exchange_id)
    )
    temporary.write_bytes(b"foreign or unproven original temporary")
    done = StorageResolverTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    ).execute(close, b"evidence", guard(60))
    assert (
        done.result.snapshot is not None
        and not done.result.snapshot.entries[-1].reusable
    )
    assert done.result.reply.resolution is not None
    assert done.result.reply.resolution.cleanup_state == "failed"
    assert temporary.read_bytes() == b"foreign or unproven original temporary"


def test_corruption_records_unknown_with_original_error(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources)
    assert cmd.io is not None
    (tmp_path / "data" / "blobs" / cmd.io.reference.sha256).write_bytes(b"corrupt")
    with pytest.raises(StorageResolverFailure) as failed:
        StorageResolverTransport(
            str(installed_sources.executable), ExplicitAdmission(cmd)
        ).execute(close, b"evidence", guard(60))
    result = failed.value.result
    assert (
        result is not None
        and result.reply.error is not None
        and result.snapshot is None
    )
    assert (
        result.reply.resolution is not None
        and result.reply.resolution.object_state == "unknown"
    )


def test_exact_replay_reads_original_resolution_without_new_inspection(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources)
    resolver = StorageResolverTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    )
    first = resolver.execute(close, b"evidence", guard(60))
    (tmp_path / "data").rename(tmp_path / "old-data")
    repeated = resolver.execute(close, b"evidence", guard(60))
    assert repeated.result.snapshot == first.result.snapshot
    assert repeated.result.reply.resolution == first.result.reply.resolution
    assert not (tmp_path / "data").exists()


def test_wrong_original_reap_is_rejected_without_history_change(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    cmd, close = setup_exchange(tmp_path, installed_sources)
    assert close.ending is not None
    close = close.model_copy(
        update={
            "ending": close.ending.model_copy(
                update={"process_id": close.ending.process_id + 100}
            )
        }
    )
    path = (
        tmp_path / "sessions" / (cmd.binding.namespace_key + ".evidence-session.json")
    )
    before = path.read_bytes()
    with pytest.raises(StorageResolverFailure) as failed:
        StorageResolverTransport(
            str(installed_sources.executable), ExplicitAdmission(cmd)
        ).execute(close, b"evidence", guard(60))
    assert (
        failed.value.result is not None
        and failed.value.result.reply.phase == "original_termination"
    )
    assert path.read_bytes() == before
