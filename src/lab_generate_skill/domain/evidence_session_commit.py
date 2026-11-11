"""Unconfirmed session commit retains candidate facts, never dispatch permission."""

from .errors import EvidenceError
from .evidence_session_state import EvidenceSessionSnapshot


class EvidenceSessionCommitUnconfirmed(EvidenceError):
    """Original cause contains all write/cleanup failures; inspect durable history.

    Candidate is the attempted state, NOT evidence it committed. A failed begin
    must never authorize data I/O, even if a later read finds this candidate.
    """

    def __init__(self, candidate: EvidenceSessionSnapshot) -> None:
        self.candidate = candidate
        super().__init__(
            "Evidence session commit unconfirmed; reconcile original facts"
        )
