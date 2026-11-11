"""Real supervised child, abrupt exit and original durable state across restart.

Test bootstrap uses explicit source/fixture paths and synthetic authority; this
is not installed-release admission or a real Slurm-writer recovery permission.
"""

import sys
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import CommandFailure, require_reaped
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.worker_protocol import decode_reply
from evidence_session_fixtures import binding
from registered_exchange_fixtures import harness
from test_slurm_commands import guard

PROGRAM = """
import os,sys
from pathlib import Path
sys.path[:0] = [sys.argv[1],sys.argv[2]]
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from registered_exchange_fixtures import parent_identity
from lab_generate_skill.adapters.storage.physical_exchange import PhysicalEvidenceExchange
from lab_generate_skill.adapters.storage.registered_exchange_result import RegisteredExchangeFailure
from lab_generate_skill.adapters.storage import evidence_worker
from lab_generate_skill.adapters.storage.worker_protocol import decode_command, decode_reply
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_session_fixtures import binding, intent
from evidence_session_storage_fixtures import store
from test_lifecycle import ManualClock, CancelSwitch
root=Path(sys.argv[3]); mode=sys.argv[4]
original=evidence_worker.exchange
def physical(raw):
    if mode == 'exit_before': os._exit(41)
    reply=original(raw)
    command,_=decode_command(raw)
    assert decode_reply(command,reply)[0].error is None
    if mode == 'exit_after': os._exit(42)
    if mode == 'blocked_after':
        os.write(2,b'unit-data-written')
        read,write=os.pipe()
        os.read(read,1)
    return reply
evidence_worker.exchange=physical
raw=sys.stdin.buffer.read()
try:
    result=registered_exchange(raw,binding(),0,store(root/'sessions'),intent().operation,
                               OperationGuards(ManualClock(),CancelSwitch()), PhysicalEvidenceExchange(raw), controller=parent_identity())
except RegisteredExchangeFailure as error:
    if error.observation.phase != 'registration': raise
    os.write(2,b'original-session-blocked')
    raise SystemExit(43)
sys.stdout.buffer.write(result.reply)
sys.stdout.buffer.flush()
"""


def argv(root: Path, mode: str) -> tuple[str, ...]:
    return (
        sys.executable,
        "-I",
        "-B",
        "-c",
        PROGRAM,
        str(Path(__file__).resolve().parents[2] / "src"),
        str(Path(__file__).parent),
        str(root),
        mode,
    )


@pytest.mark.parametrize(
    "mode,code,stage,has_data",
    [
        ("normal", 0, "returned", True),
        ("exit_before", 41, "pending", False),
        ("exit_after", 42, "pending", True),
    ],
)
def test_actual_child_exit_retains_original_identity_and_blocks_restart(
    tmp_path: Path, mode: str, code: int, stage: str, has_data: bool
) -> None:
    f = harness(tmp_path)
    capture = ProcessRunner().run(argv(tmp_path, mode), guard(15), stdin_bytes=f.raw)
    ended = require_reaped(capture)
    assert capture.returncode == code
    saved = f.ledger.read(binding(), f.op)
    assert saved.entries[0].stage == stage
    assert saved.entries[0].intent.worker.process_id == ended.process_id
    assert not saved.entries[0].reusable  # reaped alone never resolves storage
    if has_data:
        assert (
            FileEvidenceStore(tmp_path / "evidence", initialize=False).read(
                f.command.reference
            )
            == b"original"
        )
    else:
        assert not (tmp_path / "evidence" / "blobs").exists()
    if code == 0:
        assert decode_reply(f.command, capture.stdout)[0].error is None
    else:
        assert capture.stdout == b""
    repeated = ProcessRunner().run(
        argv(tmp_path, "normal"), guard(15), stdin_bytes=f.raw
    )
    assert repeated.returncode == 43 and repeated.stderr == b"original-session-blocked"
    assert f.ledger.read(binding(), f.op) == saved


def test_timeout_after_data_publication_retains_pending(tmp_path: Path) -> None:
    f = harness(tmp_path)
    with pytest.raises(CommandFailure) as failed:
        ProcessRunner().run(
            argv(tmp_path, "blocked_after"), guard(4), stdin_bytes=f.raw
        )
    assert b"unit-data-written" in failed.value.capture.stderr
    assert require_reaped(failed.value.capture).state == "reaped"
    saved = f.ledger.read(binding(), f.op)
    assert saved.entries[0].stage == "pending" and saved.entries[0].outcome is None
    assert (
        FileEvidenceStore(tmp_path / "evidence", initialize=False).read(
            f.command.reference
        )
        == b"original"
    )
