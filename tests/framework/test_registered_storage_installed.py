"""Actual installed fixed entry and durable history, synthetic business scope."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
    RegisteredStorageFailure,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    encode_registered_command,
    decode_registered_reply,
)
from registered_storage_fixtures import ExplicitAdmission, request, roots
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_installed_create_write_and_duplicate_keeps_original(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    create = request(tmp_path, create=True, installation=installed_sources)
    admission = ExplicitAdmission(create)
    made = RegisteredStorageTransport(
        str(installed_sources.executable), admission
    ).execute(create, b"", guard(60))
    assert (
        made.result.snapshot is not None
        and made.result.snapshot.revision == 0
        and admission.calls == 1
    )
    cmd = request(tmp_path, installation=installed_sources)
    admission = ExplicitAdmission(cmd)
    transport = RegisteredStorageTransport(str(installed_sources.executable), admission)
    done = transport.execute(cmd, b"evidence", guard(60))
    assert done.result.snapshot is not None and done.result.snapshot.revision == 2
    assert (
        done.result.reply.intent is not None and done.result.reply.outcome is not None
    )
    assert done.capture.termination is not None
    assert (
        done.result.reply.intent.worker.process_id
        == done.capture.termination.process_id
    )
    assert done.result.reply.outcome.status == "succeeded"
    assert not done.result.snapshot.entries[0].reusable
    files = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    with pytest.raises(RegisteredStorageFailure) as failed:
        transport.execute(cmd, b"evidence", guard(60))
    assert (
        failed.value.result is not None and failed.value.result.reply.error is not None
    )
    assert not failed.value.result.raw_reply
    assert files == {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    assert list((tmp_path / "data" / "blobs").iterdir())[0].read_bytes() == b"evidence"
    # An intact response with changed identity must not be accepted.
    altered = cmd.model_copy(
        update={"operation": cmd.operation.model_copy(update={"operation_id": "other"})}
    )
    with pytest.raises(ValueError):
        decode_registered_reply(
            encode_registered_command(altered, b"evidence"), done.capture.stdout
        )


def test_installed_missing_read_retains_failed_outcome(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    create = request(tmp_path, create=True, installation=installed_sources)
    RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(create)
    ).execute(create, b"", guard(60))
    cmd = request(tmp_path, reading=True, installation=installed_sources)
    with pytest.raises(RegisteredStorageFailure) as failed:
        RegisteredStorageTransport(
            str(installed_sources.executable), ExplicitAdmission(cmd)
        ).execute(cmd, b"", guard(60))
    result = failed.value.result
    assert result is not None and result.reply.error is None
    assert result.reply.outcome is not None and result.reply.outcome.status == "failed"
    assert result.snapshot is not None and result.snapshot.revision == 2
    assert not result.snapshot.entries[0].reusable
    assert not (tmp_path / "data" / "blobs").exists()


def test_denied_admission_never_launches_or_creates(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    class Denied(ExplicitAdmission):
        def authorize_storage(self, *args: object, **kwargs: object) -> None:
            raise PermissionError("denied")

    cmd = request(tmp_path, create=True, installation=installed_sources)
    with pytest.raises(PermissionError):
        RegisteredStorageTransport(
            str(installed_sources.executable), Denied(cmd)
        ).execute(cmd, b"", guard(30))
    assert list(tmp_path.iterdir()) == []


def test_canonical_root_alias_rejected_without_creating_history(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    (tmp_path / "data").rmdir()
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "data").symlink_to(real, target_is_directory=True)
    cmd = request(tmp_path, create=True, installation=installed_sources)
    with pytest.raises(RegisteredStorageFailure) as failed:
        RegisteredStorageTransport(
            str(installed_sources.executable), ExplicitAdmission(cmd)
        ).execute(cmd, b"", guard(60))
    assert (
        failed.value.result is not None
        and failed.value.result.reply.phase == "configuration"
    )
    assert list((tmp_path / "sessions").iterdir()) == [] and list(real.iterdir()) == []


@pytest.mark.parametrize("payload", [b"", b"\x00\xff\n"])
def test_installed_read_returns_exact_empty_or_binary_bytes(
    tmp_path: Path, installed_sources: InstalledFixture, payload: bytes
) -> None:
    from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
    from lab_generate_skill.adapters.storage.worker_protocol import decode_reply
    from evidence_worker_fixtures import command

    roots(tmp_path)
    put = command(tmp_path / "data", payload)
    assert put.metadata is not None
    FileEvidenceStore(tmp_path / "data").put(payload, put.metadata)
    create = request(tmp_path, create=True, installation=installed_sources)
    RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(create)
    ).execute(create, b"", guard(60))
    io = put.model_copy(
        update={"operation": "read", "metadata": None, "max_object_bytes": 1024}
    )
    cmd = request(tmp_path, reading=True, installation=installed_sources).model_copy(
        update={"io": io}
    )
    result = RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(cmd)
    ).execute(cmd, b"", guard(60))
    assert decode_reply(io, result.result.raw_reply)[1] == payload
    assert (
        result.result.snapshot is not None
        and not result.result.snapshot.entries[-1].reusable
    )
