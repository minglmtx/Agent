"""Real file/session composition with an explicitly synthetic authority."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.storage.session_exchange import registered_exchange
from lab_generate_skill.adapters.storage.physical_exchange import (
    PhysicalEvidenceExchange,
)
from lab_generate_skill.adapters.storage.registered_exchange_result import (
    RegisteredExchangeResult,
)
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from lab_generate_skill.adapters.storage.worker_protocol import encode_command
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch
from evidence_session_storage_fixtures import UnitSessionAuthority
from evidence_session_fixtures import binding, capacity, intent
from evidence_worker_fixtures import command


@dataclass
class Harness:
    root: Path
    ledger: FileEvidenceSessions
    controls: OperationGuards
    clock: ManualClock
    op: OperationContext
    command: EvidenceCommand
    raw: bytes

    def execute(self, revision: int = 0) -> RegisteredExchangeResult:
        return registered_exchange(
            self.raw,
            binding(),
            revision,
            self.ledger,
            self.op,
            self.controls,
            PhysicalEvidenceExchange(self.raw),
            controller=parent_identity(),
        )


def harness(root: Path, *, reading: bool = False, create: bool = True) -> Harness:
    ledger_root = root / "sessions"
    ledger_root.mkdir()
    (root / "evidence").mkdir()  # Trusted root provisioned by test bootstrap.
    clock = ManualClock()
    controls = OperationGuards(clock, CancelSwitch())
    b = binding()
    ledger = FileEvidenceSessions(
        ledger_root,
        b.storage_id,
        b.storage_config_sha256,
        controls,
        UnitSessionAuthority(),
    )
    op = intent().operation
    if create:
        ledger.create(b, capacity(), op)
    cmd = command(root / "evidence", b"original", "read" if reading else "put")
    raw = encode_command(cmd, b"" if reading else b"original")
    return Harness(root, ledger, controls, clock, op, cmd, raw)


def parent_identity() -> ProcessIdentity:
    """Actual parent identity for in-process engineering exchange fixtures."""
    import os
    from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
    from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
    from test_slurm_commands import guard

    return read_process_identity(KernelReadings(guard(10)), os.getppid(), os.getuid())
