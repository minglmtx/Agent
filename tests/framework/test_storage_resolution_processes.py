"""Real child crashes and read-only cleanup; synthetic business authority only.

Exit status comes from the original ProcessRunner and the intent contains the
actual child's incarnation. This is not the final installed owner/resolver entry
or production binding authority. Unknown/temporary-bearing calls stay isolated.
"""

from registered_exchange_fixtures import parent_identity

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.observed_inspection import (
    ObservedStorageInspection,
)
from lab_generate_skill.adapters.storage.worker_protocol import decode_command
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import require_reaped
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from registered_exchange_fixtures import parent_identity
from lab_generate_skill.adapters.storage.physical_exchange import (
    PhysicalEvidenceExchange,
)
from lab_generate_skill.adapters.storage.session_resolution import (
    resolve_registered_storage,
)
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from lab_generate_skill.adapters.storage.worker_protocol import encode_command
from lab_generate_skill.domain.evidence_sessions import EvidenceWorkerEnded
from evidence_session_fixtures import binding, resolution
from registered_exchange_fixtures import harness
from test_slurm_commands import guard

PROGRAM = """
import os,sys
from pathlib import Path
sys.path[:0] = [sys.argv[1],sys.argv[2]]
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from registered_exchange_fixtures import parent_identity
from lab_generate_skill.adapters.storage.physical_exchange import PhysicalEvidenceExchange
from lab_generate_skill.adapters.storage import evidence_worker
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_session_fixtures import binding, intent
from evidence_session_storage_fixtures import store
from test_lifecycle import ManualClock, CancelSwitch
root=Path(sys.argv[3]); mode=sys.argv[4]
link=os.link
if mode in ('before_publish', 'after_publish'):
    def crash(*args, **kwargs):
        if mode == 'after_publish': link(*args, **kwargs)
        os._exit(85 if mode == 'before_publish' else 86)
    os.link=crash
physical=evidence_worker.exchange
if mode == 'after_return':
    def lost(raw):
        physical(raw)
        os._exit(87)
    evidence_worker.exchange=lost
raw=sys.stdin.buffer.read()
value=registered_exchange(raw,binding(),0,store(root/'sessions'),
                          intent().operation,OperationGuards(ManualClock(),CancelSwitch()), PhysicalEvidenceExchange(raw), controller=parent_identity())
sys.stdout.buffer.write(value.reply)
"""


@pytest.mark.parametrize(
    "mode,code,temporary,present",
    [
        ("normal", 0, False, True),
        ("before_publish", 85, True, False),
        ("after_publish", 86, True, True),
        ("after_return", 87, False, True),
    ],
)
def test_actual_exit_resolution_and_next_exchange(
    tmp_path: Path, mode: str, code: int, temporary: bool, present: bool
) -> None:
    f = harness(tmp_path)
    argv = (
        sys.executable,
        "-I",
        "-B",
        "-c",
        PROGRAM,
        str(Path(__file__).resolve().parents[2] / "src"),
        str(Path(__file__).parent),
        str(tmp_path),
        mode,
    )
    capture = ProcessRunner().run(argv, guard(15), stdin_bytes=f.raw)
    ending = require_reaped(capture)
    assert ending.returncode == code and capture.stderr == b""
    before = f.ledger.read(binding(), f.op)
    original = before.entries[-1]
    assert original.intent.worker.process_id == ending.process_id
    cleanup = resolution(original.intent).operation
    ended = EvidenceWorkerEnded(
        worker=original.intent.worker,
        observed_at=datetime.now(timezone.utc),
        returncode=code,
        verifier_id="test-actual-child-reaper",
        proof_sha256=hashlib.sha256(repr(ending).encode()).hexdigest(),
    )
    result = resolve_registered_storage(
        f.raw,
        binding(),
        f.ledger,
        cleanup,
        f.controls,
        ended,
        ObservedStorageInspection(decode_command(f.raw)[0]),
    )
    assert result.snapshot is not None
    last = result.snapshot.entries[-1]
    assert last.outcome == original.outcome
    assert (last.outcome is not None) is (mode == "normal")
    assert last.stage == ("quarantined" if temporary else "resolved")
    assert result.resolution.object_state == ("present" if present else "absent")
    pending = (
        tmp_path / "evidence" / "blobs" / exchange_temporary_name(f.command.exchange_id)
    )
    assert pending.exists() is temporary
    if temporary:
        assert pending.read_bytes() == b"original"
        # The original input is not replayed; original pending identity remains.
        assert last.intent == original.intent
    else:
        read = f.command.model_copy(
            update={"exchange_id": "next-read", "operation": "read", "metadata": None}
        )
        next_result = registered_exchange(
            encode_command(read),
            binding(),
            result.snapshot.revision,
            f.ledger,
            f.op,
            f.controls,
            PhysicalEvidenceExchange(encode_command(read)),
            controller=parent_identity(),
        )
        assert next_result.outcome.status == "succeeded"
