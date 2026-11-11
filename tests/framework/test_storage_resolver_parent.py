"""Real resolver parent death during native inspection, without cleanup claims."""

import time
from hashlib import sha256
from pathlib import Path
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd
from lab_generate_skill.adapters.storage.registered_protocol import (
    encode_registered_command,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    encode_resolution_command,
    decode_resolution_reply,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from registered_storage_fixtures import request, roots
from test_storage_resolver_installed import setup_exchange
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

RESOLVER = """
import ctypes,os
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.adapters.storage import inspection
from lab_generate_skill.bootstrap.evidence_resolver import main
def native_block(command,control):
    os.write(2,(current_process_identity().model_dump_json()+'\\n').encode())
    ctypes.CDLL(None).pause()
    raise AssertionError('native inspection unexpectedly returned')
inspection.inspect_exchange_storage=native_block
raise SystemExit(main())
"""

CONTROLLER = """
import os,sys,subprocess
from datetime import datetime,timezone
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
from lab_generate_skill.adapters.storage.registered_protocol import decode_registered_command
from lab_generate_skill.adapters.storage.registered_transport import RegisteredStorageTransport
from lab_generate_skill.adapters.storage.resolver_protocol import StorageResolutionCommand,encode_resolution_command
from lab_generate_skill.bootstrap.evidence_worker import _NoCancellationChannel
from lab_generate_skill.runtime.lifecycle import OperationGuards
class ExplicitEngineeringAdmission:
    def authorize_storage(self,binding,config,operation,control):
        assert binding==original.binding and config==original.config
        assert operation.owner_id==original.operation.owner_id
        control.checkpoint()
original,payload=decode_registered_command(sys.stdin.buffer.read())
original=original.model_copy(update={'controller':current_process_identity()})
controls=OperationGuards(SystemClock(),_NoCancellationChannel())
transport=RegisteredStorageTransport(sys.executable,ExplicitEngineeringAdmission())
create=original.model_copy(update={'action':'create','io':None,'expected_revision':None,'operation':original.operation.model_copy(update={'operation_id':'create'})})
transport.execute(create,b'',controls.bind(create.operation))
executed=transport.execute(original,payload,controls.bind(original.operation))
assert executed.ending is not None
cleanup=original.operation.cleanup('close-parent-death',now=datetime.now(timezone.utc),seconds=60)
command=StorageResolutionCommand(original=original,cleanup=cleanup,ending=executed.ending)
child=subprocess.Popen([sys.executable,'-I','-B','-c',sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
try:
    child.stdin.write(encode_resolution_command(command,payload)); child.stdin.close()
    marker=child.stderr.readline()
    if not marker.startswith(b'{'):
        raise RuntimeError('resolver did not reach inspection: '+repr(marker))
    sys.stdout.buffer.write(marker); sys.stdout.buffer.flush()
    os._exit(45)
finally:
    child.kill(); child.wait(timeout=3)
"""


def test_actual_controller_death_stops_native_blocked_resolver(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    cmd = request(tmp_path, installation=installed_sources)
    capture = ProcessRunner().run(
        (str(installed_sources.executable), "-I", "-B", "-c", CONTROLLER, RESOLVER),
        guard(60),
        stdin_bytes=encode_registered_command(cmd, b"evidence"),
    )
    assert capture.returncode == 45, capture.stderr.decode(errors="replace")
    original = ProcessIdentity.model_validate_json(capture.stdout)
    stat = Path(f"/proc/{original.process_id}/stat")
    stopped = False
    try:
        until = time.monotonic() + 5
        while time.monotonic() < until:
            try:
                raw = stat.read_bytes()
            except FileNotFoundError:
                stopped = True
                break
            if parse_process_start(raw, original.process_id) != original.start_ticks:
                stopped = True
                break
            if raw.rpartition(b") ")[2].split()[0] in (b"Z", b"X"):
                stopped = True
                break
            time.sleep(0.02)
        assert stopped, "original native-blocked resolver survived controller exit"
    finally:
        if not stopped:
            try:
                with pinned_owner(original, guard(3)) as fd:
                    kill_pidfd(fd)
            except (ProcessLookupError, FileNotFoundError, OwnershipConflict):
                pass
    path = (
        tmp_path / "sessions" / (cmd.binding.namespace_key + ".evidence-session.json")
    )
    stored = EvidenceSessionSnapshot.model_validate_json(path.read_bytes())
    assert stored.revision == 2 and len(stored.entries) == 1
    entry = stored.entries[0]
    assert entry.outcome is not None and entry.outcome.status == "succeeded"
    assert not entry.resolutions and not entry.reusable
    assert cmd.io is not None
    assert (
        tmp_path / "data" / "blobs" / cmd.io.reference.sha256
    ).read_bytes() == b"evidence"


def test_resolver_wrong_parent_incarnation_preserves_original_history(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    original, command = setup_exchange(tmp_path, installed_sources)
    assert command.ending is not None
    wrong = original.controller.model_copy(
        update={"start_ticks": original.controller.start_ticks + 1}
    )
    changed = original.model_copy(update={"controller": wrong})
    command = command.model_copy(
        update={
            "original": changed,
            "ending": command.ending.model_copy(
                update={
                    "controller": wrong,
                    "request_sha256": sha256(
                        encode_registered_command(changed, b"evidence")
                    ).hexdigest(),
                }
            ),
        }
    )
    path = (
        tmp_path
        / "sessions"
        / (original.binding.namespace_key + ".evidence-session.json")
    )
    before = path.read_bytes()
    raw = encode_resolution_command(command, b"evidence")
    capture = ProcessRunner().run(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.evidence_resolver",
        ),
        guard(60),
        stdin_bytes=raw,
    )
    assert capture.returncode == 0 and not capture.stderr
    result = decode_resolution_reply(raw, capture.stdout)
    assert result.reply.phase == "parent_guard" and result.reply.error is not None
    assert result.snapshot is None and result.reply.resolution is None
    assert path.read_bytes() == before
