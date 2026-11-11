"""Installed fixed module, real bounded transport and injected blocking backend.

Fault tests instrument methods only inside a test child; deployed worker source
has no failpoint/callback input. They verify blocking pipes, not a real NFS outage.
"""

import os
import time
from pathlib import Path
from unittest.mock import patch
import pytest

from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    CommandFailure,
    require_reaped,
)
from lab_generate_skill.adapters.storage.worker_transport import EvidenceWorkerTransport
from lab_generate_skill.adapters.storage.exchange_result import (
    EvidenceExchangeFailure,
    WorkerReportedFailure,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from evidence_worker_fixtures import command
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker


@pytest.mark.parametrize("data", [b"", b"binary\0\xff" * 10000])
def test_installed_worker_roundtrip_without_parent_storage_or_path_fallback(
    installed_worker: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/deliberately/wrong/source")
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-secret-never-child")
    transport = EvidenceWorkerTransport(str(installed_worker))
    with patch(
        "lab_generate_skill.adapters.storage.filesystem.FileEvidenceStore.__init__",
        side_effect=AssertionError("parent storage I/O"),
    ):
        saved = transport.execute(command(tmp_path, data), data, guard())
        loaded = transport.execute(command(tmp_path, data, "read"), b"", guard())
    assert saved.reply.error is None and loaded.payload == data
    assert require_reaped(saved.capture).state == "reaped"
    assert require_reaped(loaded.capture).state == "reaped"
    assert saved.capture.argv[:4] == (str(installed_worker), "-I", "-B", "-m")
    assert not list((tmp_path / "blobs").glob(".pending-*"))


def test_actual_worker_error_preserves_domain_reason(
    installed_worker: Path, tmp_path: Path
) -> None:
    (tmp_path / "blobs").mkdir()
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(str(installed_worker)).execute(
            command(tmp_path, operation="read"), b"", guard()
        )
    assert caught.value.observation.phase == "worker"
    cause = caught.value.__cause__
    assert (
        isinstance(cause, WorkerReportedFailure)
        and cause.reason_code == "MISSING_EVIDENCE"
    )
    observation = caught.value.observation
    assert observation.capture is not None and not observation.isolation_required
    require_reaped(observation.capture)
    assert list((tmp_path / "blobs").iterdir()) == []


def inject_blocking_method(monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    original_run = ProcessRunner.run
    # Fixed test code; no instrumenting hooks are accepted by production worker.
    program = """
import os,sys
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.storage.evidence_worker import main
method = sys.argv[1]
original = getattr(FileEvidenceStore, method)
def blocked(self, *args, **kwargs):
    if method == 'put':
        original(self, *args, **kwargs)
    os.write(2,b'entered-blocking-backend')
    r,w = os.pipe()
    os.read(r,1)
setattr(FileEvidenceStore,method,blocked)
raise SystemExit(main())
"""

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        assert argv[1:] == (
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.adapters.storage.evidence_worker",
        )
        return original_run(
            self,
            (argv[0], "-I", "-B", "-c", program, method),
            control,
            stdin_bytes=stdin_bytes,
        )

    monkeypatch.setattr(ProcessRunner, "run", run)


def test_blocked_read_deadline_reaps_actual_child(
    installed_worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inject_blocking_method(monkeypatch, "read")
    started = time.monotonic()
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(str(installed_worker), reap_timeout=0.5).execute(
            command(tmp_path, operation="read"), b"", guard(3)
        )
    assert time.monotonic() - started < 8
    cause = caught.value.__cause__
    assert (
        isinstance(cause, CommandFailure) and cause.reason_code == "DEADLINE_EXCEEDED"
    )
    observation = caught.value.observation
    assert observation.phase == "transport" and observation.capture is not None
    assert b"entered-blocking-backend" in observation.capture.stderr
    ended = require_reaped(observation.capture)
    assert ended.kill_requested and ended.process_id is not None
    with pytest.raises(ProcessLookupError):
        os.kill(ended.process_id, 0)


@pytest.mark.parametrize("stop", ["deadline", "cancel"])
def test_publication_then_stop_keeps_identity_without_retry(
    installed_worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    put = command(tmp_path)
    published = tmp_path / "blobs" / put.reference.sha256

    class CancelAfterPublication:
        underlying = guard(5)

        def checkpoint(self) -> float:
            if published.exists():
                raise OperationStopped("CANCELLED", "original-put")
            return self.underlying.checkpoint()

        def wait(self, seconds: float) -> None:
            self.underlying.wait(seconds)

    inject_blocking_method(monkeypatch, "put")
    control: OperationControl = (
        guard(3) if stop == "deadline" else CancelAfterPublication()
    )
    with pytest.raises(EvidenceExchangeFailure) as caught:
        EvidenceWorkerTransport(str(installed_worker), reap_timeout=0.5).execute(
            put, b"evidence", control
        )
    assert published.read_bytes() == b"evidence"
    observation = caught.value.observation
    assert observation.command.reference == put.reference and observation.reply is None
    assert observation.capture is not None
    require_reaped(observation.capture)
    cause = caught.value.__cause__
    assert isinstance(cause, CommandFailure)
    assert cause.reason_code == (
        "DEADLINE_EXCEEDED" if stop == "deadline" else "CANCELLED"
    )
    assert not list((tmp_path / "blobs").glob(".pending-*"))
    # Read back the original object with a fresh bounded operation, no put retry.
    monkeypatch.undo()
    read = EvidenceWorkerTransport(str(installed_worker)).execute(
        command(tmp_path, operation="read"), b"", guard()
    )
    assert read.payload == b"evidence"
