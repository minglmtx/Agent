"""Actual immutable file validation and fault/cleanup invariants on compute node."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.releases.files import verify_release_files
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from release_fixtures import frozen
from test_slurm_commands import guard
from test_atomic_snapshot import flatten


def test_actual_files_and_repeat_verification_are_read_only(tmp_path: Path) -> None:
    m = frozen(tmp_path / "release")
    first = verify_release_files(m, tmp_path, guard())
    assert first.file_count == 2 and first.byte_count == 7
    assert first == verify_release_files(m, tmp_path, guard())
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")} == {
        "release",
        "release/bin",
        "release/module.py",
        "release/bin/worker",
    }


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "same_size_corrupt",
        "wrong_size",
        "writable",
        "execute",
        "link",
        "directory_link",
        "fifo",
        "writable_dir",
    ],
)
def test_changed_or_unsafe_files_rejected(tmp_path: Path, fault: str) -> None:
    root = tmp_path / "release"
    m = frozen(root)
    root.chmod(0o755)
    target = root / "module.py"
    if fault == "missing":
        target.unlink()
    elif fault == "extra":
        (root / "extra").write_bytes(b"x")
        (root / "extra").chmod(0o444)
    elif fault in ("same_size_corrupt", "wrong_size"):
        target.chmod(0o644)
        target.write_bytes(b"nope" if fault == "same_size_corrupt" else b"wrong")
        target.chmod(0o444)
    elif fault == "writable":
        target.chmod(0o644)
    elif fault == "execute":
        target.chmod(0o555)
    elif fault == "link":
        target.unlink()
        target.symlink_to(root / "bin/worker")
    elif fault == "directory_link":
        (root / "alias").symlink_to(root / "bin", target_is_directory=True)
    elif fault == "fifo":
        os.mkfifo(root / "fifo")
    if fault != "writable_dir":
        root.chmod(0o555)
    with pytest.raises(EvidenceIntegrityError):
        verify_release_files(m, tmp_path, guard())


def test_outside_workspace_and_root_alias_rejected(tmp_path: Path) -> None:
    m = frozen(tmp_path / "release")
    sub = tmp_path / "workspace"
    sub.mkdir()
    with pytest.raises(EvidenceIntegrityError):
        verify_release_files(m, sub, guard())
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(EvidenceIntegrityError):
        verify_release_files(m, alias, guard())


def test_expired_operation_does_not_read_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = frozen(tmp_path / "release")

    def no_read(*args: object, **kwargs: object) -> int:
        raise AssertionError("must stop first")

    monkeypatch.setattr(os, "open", no_read)
    with pytest.raises(OperationStopped):
        verify_release_files(m, tmp_path, guard(-1))


def test_read_and_close_failure_both_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = frozen(tmp_path / "release")
    realclose = os.close

    def fail_read(fd: int, size: int) -> bytes:
        raise OSError("original read")

    def close_then_fail(fd: int) -> None:
        realclose(fd)
        raise OSError("cleanup close")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "read", fail_read)
        scoped.setattr(os, "close", close_then_fail)
        with pytest.raises(BaseExceptionGroup) as failure:
            verify_release_files(m, tmp_path, guard())
    assert [str(e) for e in flatten(failure.value)] == [
        "original read",
        "cleanup close",
    ]


@pytest.mark.parametrize("restore_timestamp", [False, True])
def test_previously_hashed_file_change_is_detected_at_final_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restore_timestamp: bool
) -> None:
    root = tmp_path / "release"
    m = frozen(root)
    realread = os.read
    changed = False

    def mutate_prior_file(fd: int, size: int) -> bytes:
        nonlocal changed
        if not changed and os.readlink(f"/proc/self/fd/{fd}").endswith("/bin/worker"):
            target = root / "module.py"
            original = target.stat()
            target.chmod(0o644)
            target.write_bytes(b"evil")
            if restore_timestamp:
                os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
            target.chmod(0o444)
            changed = True
        return realread(fd, size)

    monkeypatch.setattr(os, "read", mutate_prior_file)
    with pytest.raises(EvidenceIntegrityError):
        verify_release_files(m, tmp_path, guard())
    assert changed and (root / "module.py").read_bytes() == b"evil"
