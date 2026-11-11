"""Observed registration/reply facts, separate from execution and permissions."""

from dataclasses import dataclass
from lab_generate_skill.adapters.processes.exception_facts import exception_chain
from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot


@dataclass(frozen=True)
class RegisteredExchangeObservation:
    phase: str
    intent: EvidenceOperationIntent | None
    reply: bytes | None
    outcome: EvidenceOperationOutcome | None


class RegisteredExchangeFailure(EvidenceError):
    """Keep original registration/reply/cause; never infer nonexecution or retry."""

    def __init__(self, observation: RegisteredExchangeObservation) -> None:
        self.observation = observation
        super().__init__(
            "Registered evidence exchange failed; reconcile original session"
        )


@dataclass(frozen=True)
class RegisteredExchangeResult:
    intent: EvidenceOperationIntent
    outcome: EvidenceOperationOutcome
    reply: bytes
    snapshot: EvidenceSessionSnapshot


def retained_registered_exchange(
    error: BaseException,
) -> RegisteredExchangeObservation | None:
    """Find original reply facts through cleanup groups without losing the group."""
    for current in exception_chain(error):
        if isinstance(current, RegisteredExchangeFailure):
            return current.observation
        observed = getattr(current, "registered_exchange", None)
        if isinstance(observed, RegisteredExchangeObservation):
            return observed
    return None
