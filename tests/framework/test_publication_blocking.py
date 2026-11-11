"""Actual native blocked readonly child is killed/reaped on cancellation/deadline."""

import json
import time
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    retained_capture,
    require_reaped,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.adapters.storage.publication_protocol import (
    encode_publication_command,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from installed_publication_fixtures import setup
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

BLOCKED = """
import ctypes,os,sys
from pathlib import Path
from lab_generate_skill.adapters.releases.current import FileReleaseCurrent
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.bootstrap.storage_publication import main
def blocked(self,op):
    marker=Path(sys.argv[1])
    pending=marker.with_suffix(".pending")
    pending.write_text(current_process_identity().model_dump_json())
    pending.replace(marker)
    os.write(2,b'PUBLICATION_NATIVE_BLOCKED\\n')
    ctypes.CDLL(None).pause()
    raise AssertionError('native block returned')
FileReleaseCurrent.read=blocked
raise SystemExit(main())
"""


class StopAfterMarker:
    def __init__(self, base: OperationControl, marker: Path, mode: str) -> None:
        self.base, self.marker, self.mode = base, marker, mode
        self.first: float | None = None

    def checkpoint(self) -> float:
        remaining = self.base.checkpoint()
        if self.marker.exists():
            now = time.monotonic()
            if self.first is None:
                self.first = now
            if self.mode == "cancel" or now - self.first >= 0.2:
                raise OperationStopped(
                    "CANCELLED" if self.mode == "cancel" else "DEADLINE_EXCEEDED",
                    "publication-read",
                )
            return min(remaining, 0.2 - (now - self.first))
        return remaining

    def wait(self, seconds: float) -> None:
        self.base.wait(min(seconds, self.checkpoint()))
        self.checkpoint()


@pytest.mark.parametrize("mode", ["cancel", "deadline"])
def test_native_blocked_child_bounded_exit(
    tmp_path: Path, installed_sources: InstalledFixture, mode: str
) -> None:
    _, _, command = setup(tmp_path, installed_sources)
    root = Path(command.root)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    marker = tmp_path / "blocked.json"
    with pytest.raises(RuntimeError) as caught:
        ProcessRunner(max_output_bytes=13 * 1024 * 1024).run(
            (str(installed_sources.executable), "-I", "-B", "-c", BLOCKED, str(marker)),
            StopAfterMarker(guard(30), marker, mode),
            stdin_bytes=encode_publication_command(command),
        )
    captured = retained_capture(caught.value)
    assert captured is not None and marker.exists()
    ended = require_reaped(captured)
    assert (
        ended.kill_requested
        and ended.process_id == json.loads(marker.read_text())["process_id"]
    )
    assert not captured.complete
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


CONTROLLER = """
import os,sys,subprocess
from pathlib import Path
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.adapters.storage.publication_protocol import decode_publication_command,encode_publication_command
command=decode_publication_command(sys.stdin.buffer.read())
command=command.model_copy(update={'scope':command.scope.model_copy(update={'writer':current_process_identity()})})
child=subprocess.Popen([sys.executable,'-I','-B','-c',sys.argv[1],sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
try:
    child.stdin.write(encode_publication_command(command));child.stdin.close()
    if child.stderr.readline()!=b'PUBLICATION_NATIVE_BLOCKED\\n':
        raise RuntimeError('child did not reach actual readonly boundary')
    print(Path(sys.argv[2]).read_text(),flush=True)
    os._exit(45)
finally:
    child.kill();child.wait(timeout=3)
"""


def test_parent_exit_stops_native_reader(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    from lab_generate_skill.domain.process_identity import ProcessIdentity
    from lab_generate_skill.adapters.processes.worker_identity import (
        parse_process_start,
    )
    from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
    from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd
    from lab_generate_skill.domain.errors import OwnershipConflict

    _, _, command = setup(tmp_path, installed_sources)
    root = Path(command.root)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    marker = tmp_path / "blocked.json"
    captured = ProcessRunner().run(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-c",
            CONTROLLER,
            BLOCKED,
            str(marker),
        ),
        guard(30),
        stdin_bytes=encode_publication_command(command),
    )
    assert captured.returncode == 45, captured.stderr.decode(errors="replace")
    worker = ProcessIdentity.model_validate_json(captured.stdout)
    stopped = False
    try:
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                raw = Path(f"/proc/{worker.process_id}/stat").read_bytes()
            except FileNotFoundError:
                stopped = True
                break
            if parse_process_start(
                raw, worker.process_id
            ) != worker.start_ticks or raw.rpartition(b") ")[2].split()[0] in (
                b"Z",
                b"X",
            ):
                stopped = True
                break
            time.sleep(0.02)
        assert stopped, "native publication reader survived original controller"
    finally:
        if not stopped:
            try:
                with pinned_owner(worker, guard(3)) as fd:
                    kill_pidfd(fd)
            except (ProcessLookupError, FileNotFoundError, OwnershipConflict):
                pass
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("mode", ["cancel", "deadline"])
def test_public_reader_propagates_caller_control_to_native_block(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    from lab_generate_skill.adapters.storage.publication_reader import (
        StoragePublicationReader,
    )
    from lab_generate_skill.adapters.storage.publication_transport import (
        PublicationReadFailure,
    )
    from lab_generate_skill.runtime.lifecycle import OperationGuards
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.adapters.processes.capture import CommandCapture
    from test_run_journal import CancelSwitch

    launch, _, command = setup(tmp_path, installed_sources)
    marker = tmp_path / "blocked.json"
    run = ProcessRunner.run

    def injected(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        # Fault injection changes only the child program used in this test. The
        # actual normal-entry tests separately require the fixed -m argv.
        return run(
            self,
            (argv[0], "-I", "-B", "-c", BLOCKED, str(marker)),
            control,
            stdin_bytes=stdin_bytes,
        )

    monkeypatch.setattr(ProcessRunner, "run", injected)
    reader = StoragePublicationReader(
        Path(command.root), launch, OperationGuards(SystemClock(), CancelSwitch())
    )
    before = {
        p.name: p.read_bytes() for p in Path(command.root).iterdir() if p.is_file()
    }
    with pytest.raises(PublicationReadFailure) as caught:
        reader.read(command.operation, control=StopAfterMarker(guard(30), marker, mode))
    assert marker.exists() and caught.value.capture is not None
    ended = require_reaped(caught.value.capture)
    assert (
        ended.kill_requested
        and ended.process_id == json.loads(marker.read_text())["process_id"]
    )
    assert reader.last_execution is None
    assert {
        p.name: p.read_bytes() for p in Path(command.root).iterdir() if p.is_file()
    } == before
