"""One original physical exchange and its actual reply, shared with authority."""

import hashlib
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.evidence_sessions import EvidenceOperationOutcome
from lab_generate_skill.domain.lifecycle import OperationContext
from . import evidence_worker
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from .worker_protocol import decode_command, decode_reply


def outcome_from_reply(
    command: EvidenceCommand, raw: bytes, op: OperationContext
) -> EvidenceOperationOutcome:
    parsed, _ = decode_reply(command, raw)
    return EvidenceOperationOutcome(
        outcome_id="outcome-"
        + hashlib.sha256(command.exchange_id.encode()).hexdigest(),
        exchange_id=command.exchange_id,
        operation=op,
        reply_sha256=hashlib.sha256(raw).hexdigest(),
        status="succeeded" if parsed.error is None else "failed",
        reason_code=None if parsed.error is None else "EVIDENCE_WORKER_FAILED",
    )


class PhysicalEvidenceExchange:
    def __init__(self, raw: bytes) -> None:
        decode_command(raw)
        self._raw = raw
        self._attempted = False
        self._reply: bytes | None = None

    @property
    def raw(self) -> bytes:
        return self._raw

    @property
    def reply(self) -> bytes | None:
        return self._reply

    def execute(self, raw: bytes) -> bytes:
        if type(raw) is not bytes or raw != self._raw:
            raise OwnershipConflict("Physical exchange belongs to another command")
        if self._attempted:
            raise DispatchAlreadyCommitted("Physical exchange was already attempted")
        self._attempted = True
        self._reply = evidence_worker.exchange(raw)
        return self._reply
