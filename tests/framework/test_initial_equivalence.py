"""Declared equivalence, not byte identity; source remains immutable."""

from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.baseline import assemble_baseline
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.state_checks import StateChecks
from context_contract_fixtures import equivalence_inputs
from retrieval_fixtures import reference
from state_contract_fixtures import checks
from test_run_journal import command


def test_equivalent_different_observation_and_measurement_roundtrip_and_replay() -> (
    None
):
    inputs = equivalence_inputs()
    operation = command("equivalence", attempt="candidate")
    original = inputs.source_inputs.model_dump_json()
    receipt = assemble_equivalence(inputs, operation)
    assert receipt.status == "equivalent"
    assert (
        inputs.candidate.observation_ref
        != inputs.source_inputs.baseline.observation_ref
    )
    assert (
        inputs.candidate.measured_state_sha256
        != inputs.source_inputs.baseline.measured_state_sha256
    )
    assert inputs.candidate.scope.context_id != inputs.source.scope.context_id
    assert inputs.source_inputs.model_dump_json() == original
    assert (
        assemble_equivalence(
            EquivalenceInputs.model_validate_json(inputs.model_dump_json()), operation
        )
        == receipt
    )
    assert EquivalenceReceipt.model_validate_json(receipt.model_dump_json()) == receipt


@pytest.mark.parametrize("baseline_status", ["pass", "fail", "unknown", "missing"])
@pytest.mark.parametrize("comparison_status", ["pass", "fail", "unknown", "missing"])
def test_each_status_combination_preserves_unknown_and_failure(
    baseline_status: str, comparison_status: str
) -> None:
    inputs = equivalence_inputs()
    initial = inputs.candidate_inputs.initial
    changed_checks = (
        ()
        if baseline_status == "missing"
        else tuple(
            c.model_copy(update={"status": baseline_status})
            for c in initial.checks.checks
        )
    )
    candidate_inputs = inputs.candidate_inputs.model_copy(
        update={
            "initial": initial.model_copy(
                update={
                    "checks": StateChecks(
                        required=initial.checks.required, checks=changed_checks
                    )
                }
            )
        }
    )
    baseline = assemble_baseline(candidate_inputs, inputs.candidate.operation)
    baseline_ref = reference(baseline, baseline.schema_version)
    comparison = inputs.checks.checks
    changed_comparison = (
        ()
        if comparison_status == "missing"
        else tuple(
            c.model_copy(update={"status": comparison_status})
            for c in comparison.checks
        )
    )
    facts = inputs.checks.model_copy(
        update={
            "candidate_baseline_ref": baseline_ref,
            "checks": StateChecks(
                required=comparison.required, checks=changed_comparison
            ),
        }
    )
    inputs = inputs.model_copy(
        update={
            "candidate_inputs": candidate_inputs,
            "candidate": baseline,
            "candidate_ref": baseline_ref,
            "checks": facts,
        }
    )
    expected = "equivalent"
    if baseline_status in ("unknown", "missing") or comparison_status in (
        "unknown",
        "missing",
    ):
        expected = "unknown"
    elif "fail" in (baseline_status, comparison_status):
        expected = "rejected"
    assert (
        assemble_equivalence(inputs, command("equivalence", attempt="candidate")).status
        == expected
    )


@pytest.mark.parametrize(
    "fault",
    [
        "source_status",
        "candidate_status",
        "same_attempt",
        "source_ref",
        "candidate_ref",
        "check_scope",
        "coverage",
        "spec",
        "public_task",
        "owner",
        "run",
    ],
)
def test_mixed_or_forged_comparison_rejected(fault: str) -> None:
    inputs = equivalence_inputs()
    if fault == "source_status":
        inputs = inputs.model_copy(
            update={
                "source": inputs.source.model_copy(
                    update={"equivalence_scope": ("other",)}
                )
            }
        )
    elif fault == "candidate_status":
        inputs = inputs.model_copy(
            update={
                "candidate": inputs.candidate.model_copy(update={"status": "rejected"})
            }
        )
    elif fault == "same_attempt":
        inputs = inputs.model_copy(
            update={
                "candidate_inputs": inputs.source_inputs.baseline_inputs,
                "candidate": inputs.source_inputs.baseline,
            }
        )
    elif fault in ("source_ref", "candidate_ref"):
        ref = getattr(inputs, fault)
        inputs = inputs.model_copy(
            update={fault: reference({"wrong": True}, ref.content_schema)}
        )
    elif fault == "check_scope":
        inputs = inputs.model_copy(
            update={
                "checks": inputs.checks.model_copy(
                    update={
                        "scope": inputs.checks.scope.model_copy(
                            update={"context_id": "wrong"}
                        )
                    }
                )
            }
        )
    elif fault == "coverage":
        inputs = inputs.model_copy(
            update={
                "checks": inputs.checks.model_copy(
                    update={"checks": checks(("other",))}
                )
            }
        )
    elif fault == "spec":
        inputs = inputs.model_copy(
            update={
                "candidate": inputs.candidate.model_copy(
                    update={"spec_ref": reference({}, "initial-state-spec/1")}
                )
            }
        )
    elif fault == "public_task":
        changed = inputs.candidate_inputs.public_task.model_copy(
            update={"goal": "other goal"}
        )
        candidate_inputs = inputs.candidate_inputs.model_copy(
            update={
                "public_task": changed,
                "prepared": inputs.candidate_inputs.prepared.model_copy(
                    update={"public_task": changed}
                ),
            }
        )
        inputs = inputs.model_copy(update={"candidate_inputs": candidate_inputs})
    else:
        # Source receipt remains structurally valid for the other owner/run, but
        # cannot replace the frozen source facts or authorize this candidate.
        field = "owner_id" if fault == "owner" else "run_id"
        source = inputs.source.model_copy(
            update={
                "scope": inputs.source.scope.model_copy(
                    update={
                        "owner": inputs.source.scope.owner.model_copy(
                            update={field: "other"}
                        )
                    }
                ),
                "operation": inputs.source.operation.model_copy(
                    update={field: "other"}
                ),
            }
        )
        inputs = inputs.model_copy(update={"source": source})
    with pytest.raises(OwnershipConflict):
        assemble_equivalence(inputs, command("equivalence", attempt="candidate"))


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "owner",
        "attempt",
        "run_level",
        "cleanup",
        "reuse_baseline",
        "reuse_checks",
        "reuse_source",
        "reuse_closure",
    ],
)
def test_comparison_operation_boundaries(fault: str) -> None:
    inputs = equivalence_inputs()
    changes: dict[str, dict[str, object]] = {
        "run": {"run_id": "other"},
        "owner": {"owner_id": "other"},
        "attempt": {"attempt_id": "other"},
        "run_level": {"attempt_id": None},
        "cleanup": {"mode": "cleanup", "parent_operation_id": "original"},
        "reuse_baseline": {"operation_id": inputs.candidate.operation.operation_id},
        "reuse_checks": {"operation_id": inputs.checks.operation.operation_id},
        "reuse_source": {"operation_id": inputs.source.operation.operation_id},
        "reuse_closure": {
            "operation_id": inputs.source_inputs.reset_inputs.closures[0].operation_id
        },
    }
    with pytest.raises(OwnershipConflict):
        assemble_equivalence(
            inputs,
            command("equivalence", attempt="candidate").model_copy(
                update=changes[fault]
            ),
        )


@pytest.mark.parametrize("bad", [None, {}, [], True, "comparison", 1])
def test_invalid_comparison_root(bad: object) -> None:
    with pytest.raises(ValidationError):
        assemble_equivalence(
            cast(EquivalenceInputs, bad), command("equivalence", attempt="candidate")
        )


@pytest.mark.parametrize("field", ["source_ref", "candidate_ref", "checks_ref"])
@pytest.mark.parametrize("fault", ["visibility", "schema"])
def test_comparison_private_schema_boundaries(field: str, fault: str) -> None:
    inputs = equivalence_inputs()
    ref = getattr(inputs, field)
    change = (
        {"visibility": "public"}
        if fault == "visibility"
        else {"content_schema": "obsolete/1"}
    )
    if field == "checks_ref":
        inputs = inputs.model_copy(update={field: ref.model_copy(update=change)})
    else:
        nested = (
            "source_context_receipt_ref"
            if field == "source_ref"
            else "candidate_baseline_ref"
        )
        inputs = inputs.model_copy(
            update={
                field: ref.model_copy(update=change),
                "checks": inputs.checks.model_copy(
                    update={nested: ref.model_copy(update=change)}
                ),
            }
        )
    with pytest.raises(ValidationError):
        assemble_equivalence(inputs, command("equivalence", attempt="candidate"))


def test_large_replacement_policy_cannot_bypass_frozen_coverage() -> None:
    inputs = equivalence_inputs()
    required = tuple("check-" + str(i) for i in range(1024))
    # A larger source policy is propagated through both complete baseline graphs.
    source_inputs = inputs.source_inputs
    spec = source_inputs.baseline_inputs.spec.model_copy(
        update={"equivalence_checks": required}
    )
    spec_ref = reference(spec, spec.schema_version)
    # Policy substitution only in a summary is rejected; full graph updates are
    # required, so a caller cannot widen/narrow it during comparison.
    with pytest.raises(OwnershipConflict):
        assemble_equivalence(
            inputs.model_copy(
                update={
                    "source": inputs.source.model_copy(
                        update={"spec_ref": spec_ref, "equivalence_scope": required}
                    ),
                    "checks": inputs.checks.model_copy(
                        update={"checks": checks(required)}
                    ),
                }
            ),
            command("equivalence", attempt="candidate"),
        )
