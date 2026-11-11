"""Observed evidence exchange facts, distinct from durable session isolation.

An expected reference survives transport failure. A parsed reply, zero exit or
reaped child alone never authorizes replay, recovery or a clean-resource receipt.
"""

from dataclasses import dataclass
from typing import Literal

from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from .worker_protocol import EvidenceReply

ExchangePhase = Literal[
    "launch", "transport", "termination", "process", "protocol", "worker", "completion"
]


@dataclass(frozen=True)
class ExchangeObservation:
    command: EvidenceCommand
    phase: ExchangePhase
    capture: CommandCapture | None
    reply: EvidenceReply | None

    @property
    def isolation_required(self) -> bool:
        """Minimum termination isolation, not isolation itself or store health.

        False does not establish clean storage, absence of pending writes or
        permission to continue; those remain separate session-owner decisions.
        """
        ended = self.capture.termination if self.capture is not None else None
        return (
            ended is None or ended.state == "unconfirmed" or bool(ended.cleanup_errors)
        )


@dataclass(frozen=True)
class EvidenceExchangeResult:
    reply: EvidenceReply
    payload: bytes
    capture: CommandCapture


class EvidenceExchangeFailure(EvidenceError):
    reason_code = "EVIDENCE_EXCHANGE_FAILED"

    def __init__(self, observation: ExchangeObservation) -> None:
        self.observation = observation
        super().__init__(
            f"Evidence exchange {observation.command.exchange_id} failed at {observation.phase}"
        )


class WorkerReportedFailure(EvidenceError):
    """Typed remote structure, never imported/reconstructed remote exceptions."""

    def __init__(self, reply: EvidenceReply) -> None:
        if reply.error is None:
            raise ValueError("Worker failure requires a remote diagnostic")
        self.reply = reply
        self.reason_code = reply.error.reason_code or "EVIDENCE_WORKER_FAILED"
        super().__init__(f"Evidence worker reported {reply.error.type_name}")


def retained_exchange(error: BaseException) -> ExchangeObservation | None:
    if isinstance(error, EvidenceExchangeFailure):
        return error.observation
    observation = getattr(error, "evidence_exchange", None)
    if isinstance(observation, ExchangeObservation):
        return observation
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            found = retained_exchange(child)
            if found is not None:
                return found
    return None
