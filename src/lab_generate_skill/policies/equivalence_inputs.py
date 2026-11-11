"""Exact producer bodies for one equivalence publication; no I/O or authority."""

from lab_generate_skill.domain.baseline_read import baseline_documents
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.validation import Contract
from .evidence_bytes import require_complete_bytes


def checked_equivalence_bodies(
    inputs: EquivalenceInputs, receipt: EquivalenceReceipt
) -> dict[EvidenceRef, bytes]:
    inputs = EquivalenceInputs.model_validate(inputs)
    receipt = EquivalenceReceipt.model_validate(receipt)
    source = inputs.source_inputs
    if any(
        ref.visibility != "private"
        for ref in (inputs.source_ref, inputs.candidate_ref, inputs.checks_ref)
    ):
        raise OwnershipConflict(
            "Equivalence handoff requires original private root references"
        )
    if assemble_equivalence(inputs, receipt.operation) != receipt:
        raise OwnershipConflict(
            "Equivalence handoff changed original complete source/candidate/checks"
        )
    bodies: dict[EvidenceRef, bytes] = {}

    def add(ref: EvidenceRef, value: Contract) -> None:
        raw = value.model_dump_json().encode()
        if (
            ref.media_type != "application/json"
            or ref.content_schema != value.model_dump().get("schema_version")
        ):
            raise OwnershipConflict(
                "Equivalence input body changed original JSON schema"
            )
        require_complete_bytes(ref, raw)
        if ref in bodies and bodies[ref] != raw:
            raise OwnershipConflict("Equivalence input has conflicting complete bodies")
        bodies[ref] = raw

    value: Contract
    for ref, value in (
        (inputs.source_ref, inputs.source),
        (inputs.candidate_ref, inputs.candidate),
        (inputs.checks_ref, inputs.checks),
        (source.context_ref, source.context),
        (source.baseline_ref, source.baseline),
        (source.reset_ref, source.reset),
    ):
        add(ref, value)
    if inputs.adoption is not None:
        add(inputs.adoption.binding.execution_source_ref, inputs.adoption.source)
    for initial in (source.baseline_inputs, inputs.candidate_inputs):
        for ref, value in baseline_documents(initial):
            add(ref, value)
    reset = source.reset_inputs
    for ref, value in (
        (reset.plan_ref, reset.plan),
        (reset.plan.spec_ref, reset.spec),
        (reset.plan.task_recovery_ref, reset.task_recovery),
        (reset.plan.environment_recovery_ref, reset.environment_recovery),
        (reset.task_ref, reset.task),
        (reset.environment_ref, reset.environment),
        (reset.health_ref, reset.health),
    ):
        add(ref, value)
    for ref, value in zip(reset.closure_refs, reset.closures, strict=True):
        add(ref, value)
    return bodies
