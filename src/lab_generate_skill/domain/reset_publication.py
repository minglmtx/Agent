"""Same-call Reset publication bodies; never persisted or a recovery permission."""

from dataclasses import dataclass, field
import hashlib
from .errors import EvidenceIntegrityError, OwnershipConflict
from .evidence import EvidenceRef
from .reset import ResetInputs, ResetReceipt, assemble_reset
from .validation import Contract


def reset_documents(inputs: ResetInputs) -> tuple[tuple[EvidenceRef, Contract], ...]:
    return (
        (inputs.plan_ref, inputs.plan),
        (inputs.plan.spec_ref, inputs.spec),
        (inputs.plan.task_recovery_ref, inputs.task_recovery),
        (inputs.plan.environment_recovery_ref, inputs.environment_recovery),
        *tuple(zip(inputs.closure_refs, inputs.closures, strict=True)),
        (inputs.task_ref, inputs.task),
        (inputs.environment_ref, inputs.environment),
        (inputs.health_ref, inputs.health),
    )


def require_reset_bodies(receipt: ResetReceipt, inputs: ResetInputs) -> None:
    if assemble_reset(inputs, receipt.operation) != receipt:
        raise OwnershipConflict("Reset bodies changed the complete original summary")
    for reference, value in reset_documents(inputs):
        raw = value.model_dump_json().encode()
        if (reference.media_type, reference.visibility, reference.content_schema) != (
            "application/json",
            "private",
            getattr(value, "schema_version", None),
        ) or (len(raw), hashlib.sha256(raw).hexdigest()) != (
            reference.size_bytes,
            reference.sha256,
        ):
            raise EvidenceIntegrityError(
                "Reset body changed its complete original reference"
            )


@dataclass(frozen=True)
class PublishedReset:
    """Issued only after exact CAS readback by the same StateRecords adapter.

    The opaque issuer binds this in-process handoff to its publication consumer.
    It grants no owner, claim, resource, deadline or native restoration authority.
    Every consumption must still invoke the current StateAuthority.
    """

    reference: EvidenceRef
    receipt: ResetReceipt
    inputs: ResetInputs
    issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        require_reset_bodies(self.receipt, self.inputs)
        raw = self.receipt.model_dump_json().encode()
        if (
            self.reference.media_type,
            self.reference.visibility,
            self.reference.content_schema,
        ) != ("application/json", "private", "reset-receipt/1") or (
            len(raw),
            hashlib.sha256(raw).hexdigest(),
        ) != (
            self.reference.size_bytes,
            self.reference.sha256,
        ):
            raise EvidenceIntegrityError("Published Reset differs from exact readback")
