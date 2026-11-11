"""Actual fixed state entry stops after its actual controller dies in native code."""

import json
from pathlib import Path
import time
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.state_read_protocol import encode_command
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner
from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.state_read import StateReadCommand
from lab_generate_skill.domain.errors import OwnershipConflict
from admin_navigation_state_fixtures import qualified
from state_read_fixtures import reader_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

CHILD = """
import ctypes,os
from lab_generate_skill.bootstrap import state_read_worker as worker
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
class BlockedChecks:
    def environment(self,*args):
        os.write(2,current_process_identity().model_dump_json().encode()+b'\\n')
        ctypes.PyDLL(None).pause()
        raise AssertionError('native state read unexpectedly returned')
worker.bind_state_read_checks=lambda *args:BlockedChecks()
raise SystemExit(worker.main())
"""
CONTROLLER = """
import json,os,subprocess,sys
from lab_generate_skill.adapters.plans.state_read_protocol import decode_command,encode_command
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
command=decode_command(sys.stdin.buffer.read())
scope=command.scope.model_copy(update={'controller':current_process_identity()})
command=command.model_copy(update={'scope':scope})
child=subprocess.Popen([sys.executable,'-I','-B','-c',sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
try:
    child.stdin.write(encode_command(command));child.stdin.close()
    marker=child.stderr.readline()
    identity=json.loads(marker)
    if identity['process_id']!=child.pid:raise RuntimeError('wrong original state worker')
    print(json.dumps(identity),flush=True)
    os._exit(45)
finally:
    child.kill();child.wait(timeout=3)
"""


def test_actual_controller_death_stops_native_blocked_state_proof(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    installed_sources: InstalledFixture,
) -> None:
    # Compile injected fixtures before the actual fixed-entry/native boundary.
    compile(CHILD, "state-read-child", "exec")
    compile(CONTROLLER, "state-read-controller", "exec")
    with qualified(tmp_path, node_path, monkeypatch, contracts) as c:
        selection = c["environment"]
        case = reader_case(
            tmp_path / "reader",
            c["store"]._blobs.parent,
            selection.scope.task,
            installed_sources,
        )
        before = {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }
        with case.current.store.read_scope(case.controls.bind(case.operation)) as (
            scope,
            bounded,
        ):
            command = StateReadCommand(
                scope=scope,
                workspace_root=case.scope.workspace_root,
                task=selection.scope.task,
                selection=selection,
                selection_ref=c["selection_ref"],
                operation=c["operation"],
            )
            capture = ProcessRunner().run(
                (
                    str(installed_sources.executable),
                    "-I",
                    "-B",
                    "-c",
                    CONTROLLER,
                    CHILD,
                ),
                bounded,
                stdin_bytes=encode_command(command),
            )
        assert capture.returncode == 45, capture.stderr.decode(errors="replace")
        original = ProcessIdentity.model_validate_json(capture.stdout)
        stopped = False
        try:
            until = time.monotonic() + 5
            while time.monotonic() < until:
                try:
                    raw = Path(f"/proc/{original.process_id}/stat").read_bytes()
                except FileNotFoundError:
                    stopped = True
                    break
                if parse_process_start(
                    raw, original.process_id
                ) != original.start_ticks or raw.rpartition(b") ")[2].split()[0] in (
                    b"Z",
                    b"X",
                ):
                    stopped = True
                    break
                time.sleep(0.02)
            assert stopped, "Original native-blocked state worker survived its parent"
        finally:
            if not stopped:
                try:
                    with pinned_owner(original, guard(3)) as original_fd:
                        kill_pidfd(original_fd)
                except (ProcessLookupError, FileNotFoundError, OwnershipConflict):
                    pass
        assert before == {
            p.name: p.read_bytes() for p in (tmp_path / "reader/sessions").iterdir()
        }
