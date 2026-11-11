"""Check a current publisher's immutable body handoff without any I/O.

Only canonical bytes produced by the original publishers are accepted here.
Callers still check current storage/source/claim authority at the original gates;
these bodies never grant permission or qualify another task, owner or attempt.
"""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from .evidence_bytes import require_complete_bytes


def checked_publication_inputs(
    reference: EvidenceRef,
    receipt: PublicContextReceipt,
    inputs: PublicContextInputs,
) -> PublicContextInputs:
    reference = EvidenceRef.model_validate(reference)
    receipt = PublicContextReceipt.model_validate(receipt)
    inputs = PublicContextInputs.model_validate(inputs)
    if (
        reference.content_schema != receipt.schema_version
        or reference.visibility != "private"
        or reference.media_type != "application/json"
        or reference.producer != "context-records-v1"
        or assemble_public_context(inputs, receipt.operation) != receipt
    ):
        raise OwnershipConflict("Source handoff changed its complete qualification")
    initial = inputs.baseline_inputs
    for value, ref in (
        (receipt, reference),
        (inputs.context, receipt.public_context_ref),
        (inputs.baseline, receipt.baseline_ref),
        (inputs.reset, receipt.reset_ref),
        (initial.prepared, inputs.baseline.prepared_ref),
        (initial.binding, initial.prepared.task_binding_ref),
        (initial.public_task, initial.binding.public_task_ref),
    ):
        require_complete_bytes(ref, value.model_dump_json().encode())
    return inputs
