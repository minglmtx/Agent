"""Explicit synthetic authority/clock for storage tests; no real worker proofs."""

from pathlib import Path
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionResolution,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch
from evidence_session_fixtures import binding


class UnitSessionAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls: list[str] = []

    def check(self, phase: str) -> None:
        self.calls.append(phase)
        if self.denied:
            raise OwnershipConflict("unit authority denied")

    def authorize_binding(
        self, value: EvidenceSessionBinding, op: OperationContext
    ) -> None:
        self.check("binding")

    def authorize_intent(
        self, value: EvidenceSessionBinding, intent: EvidenceOperationIntent
    ) -> None:
        self.check("intent")

    def verify_outcome(
        self,
        value: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        outcome: EvidenceOperationOutcome,
        op: OperationContext,
    ) -> None:
        self.check("outcome")

    def verify_resolution(
        self,
        value: EvidenceSessionBinding,
        intent: EvidenceOperationIntent,
        resolution: EvidenceSessionResolution,
    ) -> None:
        self.check("resolution")


def store(
    root: Path, authority: UnitSessionAuthority | None = None
) -> FileEvidenceSessions:
    config = binding()
    return FileEvidenceSessions(
        root,
        config.storage_id,
        config.storage_config_sha256,
        OperationGuards(ManualClock(), CancelSwitch()),
        authority or UnitSessionAuthority(),
    )


def snapshot_path(root: Path) -> Path:
    return root / (binding().namespace_key + ".evidence-session.json")
