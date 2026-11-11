"""Register -> one physical exchange -> persist original outcome, inside worker.

This composes existing session/packet/storage implementations, not another CAS.
Bootstrap must create the session under supervision and supply real authority;
this function never creates a namespace or resolves its own worker as stopped.
All local identity, journal, permission and data I/O require outer supervision.
"""

import hashlib
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
    EvidenceSessionBinding,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.ports.evidence_sessions import EvidenceSessions
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from .physical_exchange import PhysicalEvidenceExchange, outcome_from_reply
from .worker_protocol import decode_command
from .registered_exchange_result import (
    RegisteredExchangeObservation,
    RegisteredExchangeFailure,
    RegisteredExchangeResult,
)


def registered_exchange(
    raw: bytes,
    binding: EvidenceSessionBinding,
    expected_revision: int,
    sessions: EvidenceSessions,
    op: OperationContext,
    controls: OperationControls,
    physical: PhysicalEvidenceExchange,
    *,
    controller: ProcessIdentity,
) -> RegisteredExchangeResult:
    """A returned failed worker reply stays failed; successful return isn't clean.

    begin must acknowledge exactly the next intent, never merely return a prior
    snapshot. There is no automatic create/readback/retry/cleanup. A missing ack
    stops before data effects; an outcome failure retains original encoded reply.
    A later independent resolver verifies worker termination/object/cleanup.
    """
    command, _ = decode_command(raw)  # full payload identity before any I/O
    if physical.raw != raw:
        raise OwnershipConflict("Physical capture differs from original command")
    controller = ProcessIdentity.model_validate(controller)
    binding = EvidenceSessionBinding.model_validate(binding)
    op = OperationContext.model_validate(op)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected session revision must be a nonnegative integer")
    if op.mode != "execute" or (op.run_id, op.owner_id) != (
        binding.owner.run_id,
        binding.owner.owner_id,
    ):
        raise OwnershipConflict("Exchange must retain original execute owner")
    control = controls.bind(op)
    control.checkpoint()
    phase = "identity"
    intent: EvidenceOperationIntent | None = None
    reply: bytes | None = None
    outcome: EvidenceOperationOutcome | None = None
    try:
        worker = current_evidence_worker()
        intent = EvidenceOperationIntent(
            exchange_id=command.exchange_id,
            operation=op,
            worker=worker,
            kind=command.operation,
            reference=command.reference,
            command_sha256=hashlib.sha256(raw).hexdigest(),
            command=command,
            controller=controller,
        )
        control.checkpoint()
        phase = "registration"
        registered = EvidenceSessionSnapshot.model_validate(
            sessions.begin(binding, intent, expected_revision)
        )
        if (
            registered.binding != binding
            or registered.revision != expected_revision + 1
            or not registered.entries
            or registered.entries[-1].intent != intent
            or registered.entries[-1].stage != "pending"
        ):
            raise EvidenceIntegrityError(
                "Session did not acknowledge exact original intent"
            )
        control.checkpoint()
        phase = "exchange"
        reply = physical.execute(raw)
        outcome = outcome_from_reply(command, reply, op)
        phase = "outcome"
        control.checkpoint()
        recorded = EvidenceSessionSnapshot.model_validate(
            sessions.record_outcome(binding, outcome, registered.revision, op)
        )
        if (
            recorded.binding != binding
            or recorded.capacity != registered.capacity
            or recorded.revision != registered.revision + 1
            or recorded.entries[:-1] != registered.entries[:-1]
            or recorded.entries[-1].intent != intent
            or recorded.entries[-1].outcome != outcome
            or recorded.entries[-1].resolutions
        ):
            raise EvidenceIntegrityError(
                "Session did not acknowledge exact original outcome"
            )
        phase = "completion"
        control.checkpoint()
        return RegisteredExchangeResult(intent, outcome, reply, recorded)
    except BaseException as error:
        observation = RegisteredExchangeObservation(phase, intent, reply, outcome)
        if not isinstance(error, Exception):
            setattr(error, "registered_exchange", observation)
            raise
        raise RegisteredExchangeFailure(observation) from error
