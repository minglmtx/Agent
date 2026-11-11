"""Actual installed immutable claim reads; business authority remains a fixture."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.claim_reader import StorageClaimReader
from lab_generate_skill.adapters.storage.claim_transport import ClaimReadFailure
from lab_generate_skill.adapters.storage.claim_protocol import (
    encode_claim_command,
    decode_claim_reply,
    ENTRY,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import CommandCapture, require_reaped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from claim_fixtures import UnitClaimAuthority
from test_run_journal import CancelSwitch
from test_slurm_commands import guard
from test_publication_blocking import StopAfterMarker
from test_publication_installed import CLOSE_FAULT
from installed_claim_fixtures import setup
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def contents(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_actual_read_no_parent_file_io_or_repeat_creation(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile

    scope, record, command = setup(tmp_path, installed_sources)
    before = contents(Path(command.root))

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("claim I/O escaped into controller")

    monkeypatch.setattr(AtomicSnapshotFile, "locked", forbidden)
    authority = UnitClaimAuthority()
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        authority,
    )
    for _ in range(2):
        assert (
            reader.read(record.binding.key, command.operation, control=guard(60))
            == record
        )
        observed = reader.last_execution
        assert (
            observed is not None
            and observed.reply.worker.process_id != scope.writer.process_id
        )
        assert (
            require_reaped(observed.capture).process_id
            == observed.reply.worker.process_id
        )
        assert observed.capture.argv[-2:] == ("-m", ENTRY)
    assert authority.read_calls == 2 and authority.create_calls == 0
    assert contents(Path(command.root)) == before


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "lock_missing",
        "marker_missing",
        "marker_corrupt",
        "corrupt",
        "oversize",
        "wrong_binding",
        "symlink",
        "lock_symlink",
    ],
)
def test_read_failures_leave_original_state(
    tmp_path: Path, installed_sources: InstalledFixture, case: str
) -> None:
    scope, record, command = setup(tmp_path, installed_sources)
    root = Path(command.root)
    path = root / record.binding.key.filename
    lock = root / (path.name + ".lock")
    if case == "missing":
        path.unlink()
    elif case == "lock_missing":
        lock.unlink()
    elif case == "marker_missing":
        (root / (path.name + ".initialized")).unlink()
    elif case == "marker_corrupt":
        (root / (path.name + ".initialized")).write_bytes(b"bad marker")
    elif case == "corrupt":
        path.write_bytes(b"{bad")
    elif case == "oversize":
        path.write_bytes(b" " * (128 * 1024 + 1))
    elif case == "wrong_binding":
        path.write_text(
            record.model_copy(
                update={
                    "binding": record.binding.model_copy(
                        update={"scope_id": "different"}
                    )
                }
            ).model_dump_json()
        )
    elif case == "lock_symlink":
        lock.unlink()
        lock.symlink_to(path)
    else:
        root = tmp_path / "alias"
        root.symlink_to(Path(command.root), target_is_directory=True)
    before = contents(Path(command.root))
    authority = UnitClaimAuthority()
    reader = StorageClaimReader(
        root, scope, OperationGuards(SystemClock(), CancelSwitch()), authority
    )
    with pytest.raises(ClaimReadFailure) as caught:
        reader.read(record.binding.key, command.operation, control=guard(60))
    assert caught.value.capture is not None
    observed = caught.value.reply
    assert caught.value.phase == "worker" and observed is not None
    assert (
        observed.phase == "read"
        and observed.record is None
        and observed.error is not None
    )
    expected = {
        "missing": ("EvidenceIntegrityError", "read"),
        "marker_missing": ("EvidenceIntegrityError", "read"),
        "marker_corrupt": ("EvidenceIntegrityError", "_initialized"),
        "lock_missing": ("EvidenceIntegrityError", "locked"),
        "corrupt": ("EvidenceIntegrityError", "decode_claim"),
        "oversize": ("EvidenceIntegrityError", "read"),
        "wrong_binding": ("OwnershipConflict", "decode_claim"),
        "symlink": ("OwnershipConflict", "serve_claim_read"),
        "lock_symlink": ("EvidenceIntegrityError", "locked"),
    }
    assert (observed.error.type_name, observed.error.frames[-1].function) == expected[
        case
    ]
    require_reaped(caught.value.capture)
    assert reader.last_execution is None and authority.read_calls == 0
    assert contents(Path(command.root)) == before


@pytest.mark.parametrize("bad_read", [False, True])
def test_read_and_pidfd_close_failure_retained(
    tmp_path: Path, installed_sources: InstalledFixture, bad_read: bool
) -> None:
    _, record, command = setup(tmp_path, installed_sources)
    if bad_read:
        (Path(command.root) / record.binding.key.filename).write_bytes(b"{bad")
    before = contents(Path(command.root))
    raw = encode_claim_command(command)
    observed = ProcessRunner(max_output_bytes=13 * 1024 * 1024).run(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-c",
            CLOSE_FAULT.replace("storage_publication", "storage_claim"),
        ),
        guard(30),
        stdin_bytes=raw,
    )
    reply = decode_claim_reply(raw, observed.stdout)
    assert reply.error is not None and reply.error.type_name == "ExceptionGroup"
    assert "OSError" in {child.type_name for child in reply.error.children}
    assert reply.record == (None if bad_read else record)
    assert contents(Path(command.root)) == before


BLOCKED = r"""
import ctypes,os,sys
from pathlib import Path
from lab_generate_skill.adapters.storage import claim_service
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.bootstrap.storage_claim import main
def blocked(*args):
    marker=Path(sys.argv[1]); pending=marker.with_suffix('.pending')
    pending.write_text(current_process_identity().model_dump_json()); pending.replace(marker)
    os.write(2,b'PUBLICATION_NATIVE_BLOCKED\n')
    ctypes.CDLL(None).pause()
    raise AssertionError('native block returned')
claim_service.read_claim_record=blocked
raise SystemExit(main())
"""


@pytest.mark.parametrize("mode", ["cancel", "deadline"])
def test_public_reader_native_block_uses_original_control(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    scope, record, command = setup(tmp_path, installed_sources)
    marker = tmp_path / "native.json"
    lock = Path(command.root) / (record.binding.key.filename + ".lock")
    identity = (lock.stat().st_dev, lock.stat().st_ino)
    before = contents(Path(command.root))
    run = ProcessRunner.run

    def injected(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        return run(
            self,
            (argv[0], "-I", "-B", "-c", BLOCKED, str(marker)),
            control,
            stdin_bytes=stdin_bytes,
        )

    monkeypatch.setattr(ProcessRunner, "run", injected)
    authority = UnitClaimAuthority()
    reader = StorageClaimReader(
        Path(command.root),
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        authority,
    )
    with pytest.raises(ClaimReadFailure) as caught:
        reader.read(
            record.binding.key,
            command.operation,
            control=StopAfterMarker(guard(30), marker, mode),
        )
    assert marker.exists() and caught.value.capture is not None, (
        caught.value.reply,
        caught.value.capture,
    )
    ending = require_reaped(caught.value.capture)
    assert (
        ending.kill_requested
        and ending.process_id == json.loads(marker.read_text())["process_id"]
    )
    assert reader.last_execution is None and authority.read_calls == 0
    assert contents(Path(command.root)) == before
    # The killed reader held the real stable lock. A new explicit diagnostic
    # read can acquire it without creating a replacement inode.
    monkeypatch.setattr(ProcessRunner, "run", run)
    from storage_scope_fixtures import operation

    assert (
        reader.read(
            record.binding.key, operation(scope, "diagnostic-read"), control=guard(60)
        )
        == record
    )

    assert (lock.stat().st_dev, lock.stat().st_ino) == identity
