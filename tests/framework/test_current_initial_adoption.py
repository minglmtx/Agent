"""Explicit current comparison; all native measurements/permissions are unit data."""

from pathlib import Path
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from current_initial_adoption_fixtures import current_initial_case


def test_current_adoption_preserves_complete_old_source_and_new_baseline(
    tmp_path: Path,
) -> None:
    c = current_initial_case(tmp_path / "case")
    inputs = c.inputs
    old = inputs.source_inputs.model_dump_json()
    assert inputs.source.scope.owner != inputs.candidate.scope.owner
    assert c.receipt.status == "equivalent"
    assert c.receipt.schema_version == "equivalence-receipt/2"
    assert (
        EquivalenceReceipt.model_validate_json(c.receipt.model_dump_json()) == c.receipt
    )
    assert (
        assemble_equivalence(
            EquivalenceInputs.model_validate_json(inputs.model_dump_json()),
            c.receipt.operation,
        )
        == c.receipt
    )
    assert inputs.source_inputs.model_dump_json() == old


def test_current_adoption_publishes_reads_and_hands_real_candidate_inputs(
    tmp_path: Path,
) -> None:
    c = current_initial_case(tmp_path / "case")
    op = c.receipt.operation
    ref, _ = c.records.publish_equivalence_inputs(c.receipt, c.inputs, op)
    assert c.records.load_equivalence(ref, op) == c.receipt
    assert c.records.load_context(c.inputs.source_ref, op) == c.inputs.source
    skill = c.original.plan.skill_ref
    facts = c.candidates.load(ref, skill, op)
    assert facts.equivalence == c.receipt and facts.baseline == c.inputs.candidate
    assert facts.source == c.inputs.source
    assert facts.observation.record == c.inputs.candidate_inputs.observation
