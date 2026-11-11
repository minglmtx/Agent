"""Construction transaction faults; preserve real disk state and every cause."""

from lab_generate_skill.ports.lifecycle import OperationControl

import os
from pathlib import Path
from typing import Callable

import pytest
from pydantic import TypeAdapter

from lab_generate_skill.domain.construction import CallCompleted, ProgressEvent
from lab_generate_skill.domain.construction_journal import ConstructionCommitUnconfirmed
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards

from construction_storage_fixtures import fixture
from test_atomic_snapshot import flatten
from test_construction_journal import snapshot_path
from test_run_journal import command, CancelSwitch


@pytest.mark.parametrize(
    "fault",
    ["write", "fsync", "replace", "unlink_and_close", "after_publish", "lock_close"],
)
def test_verified_fact_survives_commit_and_cleanup_faults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    progress = journal.append(event, -1, event.operation)
    result = data.event(progress)
    assert isinstance(result, CallCompleted)
    before = snapshot_path(data).read_bytes()
    realwrite, realsync, realreplace, realunlink, realclose = (
        os.write,
        os.fsync,
        os.replace,
        os.unlink,
        os.close,
    )
    published = False

    def write(fd: int, content: bytes) -> int:
        if fault == "write" and ".pending-snapshot-" in os.readlink(
            f"/proc/self/fd/{fd}"
        ):
            raise OSError("primary write")
        return realwrite(fd, content)

    def sync(fd: int) -> None:
        path = os.readlink(f"/proc/self/fd/{fd}")
        if fault == "fsync" and ".pending-snapshot-" in path:
            raise OSError("primary fsync")
        realsync(fd)
        if fault == "after_publish" and published and path == str(tmp_path / "journal"):
            raise OSError("lost directory sync ack")

    def replace(
        src: str,
        dst: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal published
        if src.startswith(".pending-snapshot-") and fault in (
            "replace",
            "unlink_and_close",
        ):
            raise OSError("primary replace")
        realreplace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        if src.startswith(".pending-snapshot-"):
            published = True

    def unlink(path: str, *, dir_fd: int | None = None) -> None:
        if path.startswith(".pending-snapshot-") and fault == "unlink_and_close":
            raise OSError("cleanup unlink")
        realunlink(path, dir_fd=dir_fd)

    def close(fd: int) -> None:
        path = os.readlink(f"/proc/self/fd/{fd}")
        realclose(fd)
        if fault == "unlink_and_close" and ".pending-snapshot-" in path:
            raise OSError("cleanup close")
        if fault == "lock_close" and path.endswith(".construction.json.lock"):
            raise OSError("lock cleanup")

    with monkeypatch.context() as scoped:
        for name, func in [
            ("write", write),
            ("fsync", sync),
            ("replace", replace),
            ("unlink", unlink),
            ("close", close),
        ]:
            scoped.setattr(os, name, func)
        with pytest.raises(ConstructionCommitUnconfirmed) as caught:
            journal.append(result, progress.revision, result.operation)
    assert (
        TypeAdapter(ProgressEvent).validate_json(
            data.store.read(caught.value.event_ref)
        )
        == result
    )
    cause = caught.value.__cause__
    assert cause is not None
    errors = [str(error) for error in flatten(cause)]
    if fault == "unlink_and_close":
        assert errors == ["primary replace", "cleanup unlink", "cleanup close"]
    else:
        assert len(errors) == 1
    reopened = data.journal().read(command())
    if fault in ("after_publish", "lock_close"):
        assert (
            reopened.events[-1] == result and reopened.revision == progress.revision + 1
        )
    else:
        assert reopened == progress and snapshot_path(data).read_bytes() == before
    # Reconcile only the exact saved fact; no model callback exists in this API.
    saved = data.journal().append(result, progress.revision, result.operation)
    assert (
        saved.events.count(result) == 1
        and saved.project().next_action.kind == "generate"
    )


def test_first_create_publish_failure_does_not_allow_empty_reinitialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("initial publication failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail)
        with pytest.raises(OSError):
            journal.create(data.plan, creation)
    assert not snapshot_path(data).exists()
    with pytest.raises(EvidenceIntegrityError):
        data.journal().create(data.plan, creation)


def test_evidence_read_failure_keeps_original_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    before = snapshot_path(data).read_bytes()

    def fail(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        raise OSError("evidence unavailable")

    with monkeypatch.context() as scoped:
        scoped.setattr(data.store, "read", fail)
        with pytest.raises(OSError, match="evidence unavailable"):
            journal.append(event, -1, event.operation)
    assert snapshot_path(data).read_bytes() == before


def test_cancelled_call_registration_stops_before_mutation(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    switch = CancelSwitch()
    switch.cancelled = True
    event = event.model_copy(
        update={
            "operation": event.operation.model_copy(
                update={
                    "cancellation_ref": CancellationRef(
                        channel_id="unit", run_id="run", owner_id="owner"
                    )
                }
            )
        }
    )
    journal.controls = OperationGuards(SystemClock(), switch)
    before = snapshot_path(data).read_bytes()
    with pytest.raises(OperationStopped, match="CANCELLED"):
        journal.append(event, -1, event.operation)
    assert snapshot_path(data).read_bytes() == before
