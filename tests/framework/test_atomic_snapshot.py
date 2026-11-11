"""Byte transaction faults and disk invariants, independently of budget rules."""

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards

from test_file_request_ledger import NoCancel, operation
from test_request_budget import request


def file(root: Path, limit: int = 100) -> AtomicSnapshotFile:
    return AtomicSnapshotFile(root, "a" * 64 + ".unit.json", max_bytes=limit)


def control() -> OperationControl:
    return OperationGuards(SystemClock(), NoCancel()).bind(operation(request()))


def flatten(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in flatten(child)]
    return [error]


def test_read_write_empty_and_expired_handle(tmp_path: Path) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        assert held.read() is None
        held.write(b"")
        assert held.read() == b""
        held.write(b"hello")
        assert held.read() == b"hello"
    with pytest.raises(OwnershipConflict):
        held.read()


@pytest.mark.parametrize("payload", [None, "abc", bytearray(b"abc"), [], b"x" * 101])
def test_bad_input_does_not_create_snapshot(tmp_path: Path, payload: object) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        with pytest.raises(ValueError):
            held.write(cast(bytes, payload))
        assert held.read() is None


@pytest.mark.parametrize("target", ["write", "fsync", "replace"])
def test_prepublication_failure_keeps_prior_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        held.write(b"old")

        def fail(*args: object, **kwargs: object) -> None:
            raise OSError(target + " failed")

        with monkeypatch.context() as scoped:
            scoped.setattr(os, target, fail)
            with pytest.raises(OSError):
                held.write(b"new")
        assert held.read() == b"old"
    assert not list(tmp_path.glob(".pending-*"))


def test_primary_unlink_and_close_errors_all_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = file(tmp_path)
    realclose = os.close

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("primary replace")

    def fail_unlink(*args: object, **kwargs: object) -> None:
        raise OSError("cleanup unlink")

    def close_then_fail(fd: int) -> None:
        temporary = ".pending-snapshot-" in os.readlink(f"/proc/self/fd/{fd}")
        realclose(fd)
        if temporary:
            raise OSError("cleanup close")

    with pytest.raises(ExceptionGroup) as caught:
        with store.locked(control()) as held:
            held.write(b"old")
            with monkeypatch.context() as scoped:
                scoped.setattr(os, "replace", fail_replace)
                scoped.setattr(os, "unlink", fail_unlink)
                scoped.setattr(os, "close", close_then_fail)
                held.write(b"new")
    errors = flatten(caught.value)
    assert [str(x) for x in errors] == [
        "primary replace",
        "cleanup unlink",
        "cleanup close",
    ]
    assert (
        len(list(tmp_path.glob(".pending-*"))) == 1
        and (tmp_path / store.name).read_bytes() == b"old"
    )


def test_read_and_close_failure_preserve_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = file(tmp_path)
    realclose = os.close
    with store.locked(control()) as held:
        held.write(b"old")

        def fail_read(fd: int, amount: int) -> bytes:
            raise OSError("primary read")

        def close_then_fail(fd: int) -> None:
            realclose(fd)
            raise OSError("read close")

        with monkeypatch.context() as scoped:
            scoped.setattr(os, "read", fail_read)
            scoped.setattr(os, "close", close_then_fail)
            with pytest.raises(ExceptionGroup) as caught:
                held.read()
    assert [str(x) for x in flatten(caught.value)] == ["primary read", "read close"]


def test_postpublication_directory_sync_failure_keeps_complete_new_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = file(tmp_path)
    realsync = os.fsync
    with store.locked(control()) as held:
        held.write(b"old")

        def sync_then_fail(fd: int) -> None:
            realsync(fd)
            if fd == held.directory:
                raise OSError("lost ack")

        with monkeypatch.context() as scoped:
            scoped.setattr(os, "fsync", sync_then_fail)
            with pytest.raises(OSError):
                held.write(b"new")
        assert held.read() == b"new"
    assert not list(tmp_path.glob(".pending-*"))


def test_short_write_and_zero_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = file(tmp_path)
    realwrite = os.write
    with store.locked(control()) as held:
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "write", lambda fd, data: realwrite(fd, data[:1]))
            held.write(b"abcd")
        assert held.read() == b"abcd"
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "write", lambda fd, data: 0)
            with pytest.raises(OSError, match="no progress"):
                held.write(b"new")
        assert held.read() == b"abcd"


def test_temporary_collision_does_not_delete_other_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = tmp_path / ".pending-snapshot-collision"
    foreign.write_bytes(b"foreign")
    monkeypatch.setattr(
        "lab_generate_skill.adapters.storage.atomic_snapshot.uuid.uuid4",
        lambda: SimpleNamespace(hex="collision"),
    )
    with file(tmp_path).locked(control()) as held:
        with pytest.raises(FileExistsError):
            held.write(b"new")
    assert foreign.read_bytes() == b"foreign"


def test_thread_transfer_and_lock_replacement_rejected(tmp_path: Path) -> None:
    store = file(tmp_path)
    errors: list[BaseException] = []
    with store.locked(control()) as held:

        def use_elsewhere() -> None:
            try:
                held.read()
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=use_elsewhere)
        thread.start()
        thread.join(2)
        assert not thread.is_alive() and isinstance(errors[0], OwnershipConflict)
        (tmp_path / (store.name + ".lock")).unlink()
        (tmp_path / (store.name + ".lock")).touch()
        with pytest.raises(OwnershipConflict):
            held.write(b"new")


def test_oversized_read_rejected(tmp_path: Path) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        held.write(b"old")
        (tmp_path / store.name).write_bytes(b"x" * 101)
        with pytest.raises(EvidenceIntegrityError):
            held.read()


@pytest.mark.parametrize("marker_fault", ["missing", "empty", "symlink", "fifo"])
def test_bad_initialization_marker_refuses_existing_data(
    tmp_path: Path, marker_fault: str
) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        held.write(b"old")
    marker = tmp_path / (store.name + ".initialized")
    marker.unlink()
    if marker_fault == "empty":
        marker.write_bytes(b"")
    elif marker_fault == "symlink":
        marker.symlink_to(tmp_path / store.name)
    elif marker_fault == "fifo":
        os.mkfifo(marker)
    with store.locked(control()) as held:
        with pytest.raises(EvidenceIntegrityError):
            held.write(b"new")
    assert (tmp_path / store.name).read_bytes() == b"old"


def test_first_publication_failure_leaves_detectable_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = file(tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("first publication failed")

    with store.locked(control()) as held:
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "replace", fail)
            with pytest.raises(OSError):
                held.write(b"new")
    assert (tmp_path / (store.name + ".initialized")).exists() and not (
        tmp_path / store.name
    ).exists()
    with store.locked(control()) as held:
        with pytest.raises(EvidenceIntegrityError):
            held.read()


def test_missing_snapshot_never_means_fresh_empty_state(tmp_path: Path) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        held.write(b"committed")
    (tmp_path / store.name).unlink()
    with store.locked(control()) as held:
        with pytest.raises(EvidenceIntegrityError):
            held.write(b"reset")


def test_pending_reference_lifecycle_and_conflict(tmp_path: Path) -> None:
    key = "b" * 64
    with file(tmp_path).locked(control()) as held:
        held.write(b"old")
        assert held.pending_keys() == () and held.pending(key) is None
        held.retain_pending(key, b"proof-ref")
        held.retain_pending(key, b"proof-ref")
        assert held.pending_keys() == (key,) and held.pending(key) == b"proof-ref"
        with pytest.raises(OwnershipConflict):
            held.retain_pending(key, b"other")
        with pytest.raises(OwnershipConflict):
            held.resolve_pending(key, b"other")
        held.resolve_pending(key, b"proof-ref")
        held.resolve_pending(key, b"proof-ref")
        assert held.pending_keys() == ()


@pytest.mark.parametrize("kind", ["empty", "large", "link", "fifo"])
def test_unsafe_pending_reference_blocks_resolution(tmp_path: Path, kind: str) -> None:
    store = file(tmp_path)
    # Establish the original namespace lock before injecting marker corruption.
    with store.locked(control()):
        pass
    key = "b" * 64
    marker = tmp_path / (store.name + ".pending-" + key)
    if kind == "empty":
        marker.write_bytes(b"")
    elif kind == "large":
        marker.write_bytes(b"x" * 8193)
    elif kind == "link":
        marker.symlink_to(tmp_path / "foreign")
    else:
        os.mkfifo(marker)
    with store.locked(control()) as held:
        assert held.pending_keys() == (key,)
        with pytest.raises(EvidenceIntegrityError):
            held.pending(key)


def test_existing_lock_mode_never_creates_missing_lock(tmp_path: Path) -> None:
    store = file(tmp_path)
    with pytest.raises(EvidenceIntegrityError):
        with store.locked(control(), create_lock=False):
            pytest.fail("missing lock admitted")
    assert list(tmp_path.iterdir()) == []
    with store.locked(control()) as held:
        held.write(b"original")
    with store.locked(control(), create_lock=False) as held:
        assert held.read() == b"original"


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_lock_creation_flag_strict_before_io(tmp_path: Path, value: object) -> None:
    with pytest.raises(TypeError):
        with file(tmp_path).locked(control(), create_lock=cast(bool, value)):
            pytest.fail("invalid flag admitted")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("retained", ["snapshot", "initialized", "pending"])
def test_missing_used_lock_is_never_recreated(tmp_path: Path, retained: str) -> None:
    store = file(tmp_path)
    with store.locked(control()) as held:
        if retained == "pending":
            held.retain_pending("b" * 64, b"original")
        else:
            held.write(b"original")
    if retained == "initialized":
        (tmp_path / store.name).unlink()
    elif retained == "snapshot":
        (tmp_path / (store.name + ".initialized")).unlink()
    lock = tmp_path / (store.name + ".lock")
    lock.unlink()
    with pytest.raises(EvidenceIntegrityError):
        with store.locked(control()):
            pass
    assert not lock.exists()
