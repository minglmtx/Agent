"""Actual controller death kills original native-blocked leaf; no recovery claim."""

import json
import time
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    encode_registered_command,
    decode_registered_reply,
)
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from registered_storage_fixtures import ExplicitAdmission, request, roots
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

CHILD = """
import ctypes,os
from lab_generate_skill.adapters.storage import evidence_worker
from lab_generate_skill.bootstrap.evidence_worker import main
def native_block(raw):
    os.write(2,b'BLOCKED_AFTER_DURABLE_BEGIN\\n')
    ctypes.CDLL(None).pause()
    raise AssertionError('native call unexpectedly returned')
evidence_worker.exchange=native_block
raise SystemExit(main())
"""
CONTROLLER = """
import os,sys,subprocess
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.adapters.storage.registered_protocol import decode_registered_command,encode_registered_command
command,payload=decode_registered_command(sys.stdin.buffer.read())
command=command.model_copy(update={'controller':current_process_identity()})
child=subprocess.Popen([sys.executable,'-I','-B','-c',sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
try:
    child.stdin.write(encode_registered_command(command,payload)); child.stdin.close()
    marker=child.stderr.readline()
    if marker!=b'BLOCKED_AFTER_DURABLE_BEGIN\\n':
        raise RuntimeError('child did not reach original registered exchange')
    print(child.pid,flush=True)
    os._exit(45)
finally:
    child.kill(); child.wait(timeout=3)
"""


def test_real_parent_death_stops_native_blocked_registered_writer(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    create = request(tmp_path, create=True, installation=installed_sources)
    RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(create)
    ).execute(create, b"", guard(60))
    cmd = request(tmp_path, installation=installed_sources)
    capture = ProcessRunner().run(
        (str(installed_sources.executable), "-I", "-B", "-c", CONTROLLER, CHILD),
        guard(30),
        stdin_bytes=encode_registered_command(cmd, b"evidence"),
    )
    assert capture.returncode == 45, capture.stderr.decode(errors="replace")
    pid = int(capture.stdout.strip())
    saved = json.loads(
        (
            tmp_path
            / "sessions"
            / (cmd.binding.namespace_key + ".evidence-session.json")
        ).read_text()
    )
    original = saved["entries"][0]
    assert original["intent"]["worker"]["process_id"] == pid
    assert original["outcome"] is None and not original["resolutions"]
    stat = Path(f"/proc/{pid}/stat")
    stopped = False
    try:
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                raw = stat.read_bytes()
            except FileNotFoundError:
                stopped = True
                break
            if (
                parse_process_start(raw, pid)
                != original["intent"]["worker"]["start_ticks"]
            ):
                stopped = True
                break  # original incarnation ended; never signal replacement
            if raw.rpartition(b") ")[2].split()[0] in (b"Z", b"X"):
                stopped = True
                break
            time.sleep(0.02)
        assert stopped, "original native-blocked leaf survived controller exit"
    finally:
        if not stopped:
            try:
                expected = ProcessIdentity.model_validate(
                    {
                        key: value
                        for key, value in original["intent"]["worker"].items()
                        if key != "schema_version"
                    }
                )
                with pinned_owner(expected, guard(3)) as original_fd:
                    kill_pidfd(original_fd)
            except (ProcessLookupError, FileNotFoundError, OwnershipConflict):
                pass
    assert not (tmp_path / "data" / "blobs").exists()
    assert (
        json.loads(
            (
                tmp_path
                / "sessions"
                / (cmd.binding.namespace_key + ".evidence-session.json")
            ).read_text()
        )
        == saved
    )


def test_leaf_rejects_wrong_parent_incarnation_before_storage(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    cmd = request(tmp_path, create=True, installation=installed_sources)
    cmd = cmd.model_copy(
        update={
            "controller": cmd.controller.model_copy(
                update={"start_ticks": cmd.controller.start_ticks + 1}
            )
        }
    )
    raw = encode_registered_command(cmd)
    capture = ProcessRunner().run(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.evidence_worker",
        ),
        guard(30),
        stdin_bytes=raw,
    )
    result = decode_registered_reply(raw, capture.stdout)
    assert result.reply.error is not None and result.reply.phase == "parent_guard"
    assert result.snapshot is None and list((tmp_path / "sessions").iterdir()) == []
