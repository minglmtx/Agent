"""Real source/candidate bytes, strict binding and mandatory semantic gates."""

from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.state_checks import StateChecks
from context_storage_fixtures import fixture
from retrieval_fixtures import reference
from test_run_journal import command


@pytest.mark.parametrize("kind", ["context", "equivalence"])
def test_publish_load_repeat_preserve_bytes_and_reverify(
    tmp_path: Path, kind: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    assert data.publish(candidate, candidate.operation) == ref
    assert data.load(kind, ref, command()) == candidate
    assert data.load(kind, ref, command(attempt="candidate")) == candidate
    assert data.store.read(ref) == candidate.model_dump_json().encode()
    assert data.authority.calls.count(kind) == 4
    assert data.authority.calls.count("reset") == 4


def test_cross_attempt_source_permission_does_not_rebind_or_relax_state_records(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    op = command("candidate-source-read", attempt="candidate")
    assert data.adapter.load_context(data.inputs.source_ref, op) == data.inputs.source
    assert data.authority.context_operations == [op]
    states = EvidenceStateRecords(data.store, data.adapter.controls, data.authority)
    with pytest.raises(OwnershipConflict, match="run/owner/attempt"):
        states.load_baseline(data.inputs.source_inputs.baseline_ref, op)
    data.authority.denied_context = True
    with pytest.raises(OwnershipConflict, match="source permission"):
        data.adapter.load_context(data.inputs.source_ref, command(attempt="candidate"))


@pytest.mark.parametrize(
    "kind,gate",
    [
        ("context", "state"),
        ("context", "context"),
        ("equivalence", "state"),
        ("equivalence", "context"),
        ("equivalence", "equivalence"),
    ],
)
def test_authority_required_for_publish_and_consume(
    tmp_path: Path, kind: str, gate: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    setattr(
        data.authority,
        {
            "state": "denied",
            "context": "denied_context",
            "equivalence": "denied_equivalence",
        }[gate],
        True,
    )
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        data.publish(candidate, candidate.operation)
    with pytest.raises(OwnershipConflict):
        data.load(kind, ref, command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
@pytest.mark.parametrize(
    "item",
    [
        "projection",
        "source_baseline",
        "source_reset",
        "private_fact",
        "protected",
        "closure",
        "observation",
        "recovery_baseline",
    ],
)
def test_actual_transitive_source_bytes_required(
    tmp_path: Path, kind: str, fault: str, item: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    ref = data.publish(candidate, candidate.operation)
    source = data.inputs.source_inputs
    targets = {
        "projection": source.context_ref,
        "source_baseline": source.baseline_ref,
        "source_reset": source.reset_ref,
        "private_fact": source.baseline_inputs.initial.checks.checks[0].evidence[0],
        "protected": data.protected_ref,
        "closure": source.reset_inputs.closure_refs[0],
        "observation": source.baseline_inputs.observation_ref,
        "recovery_baseline": source.reset_inputs.task_recovery.baseline_ref,
    }
    path = tmp_path / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    error = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(error):
        data.publish(candidate, candidate.operation)
    with pytest.raises(error):
        data.load(kind, ref, command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("item", ["candidate", "checks", "private_fact"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_actual_candidate_comparison_bytes_required(
    tmp_path: Path, item: str, fault: str
) -> None:
    data = fixture(tmp_path)
    ref = data.publish(data.comparison, data.comparison.operation)
    targets = {
        "candidate": data.comparison.candidate_baseline_ref,
        "checks": data.comparison.checks_ref,
        "private_fact": data.inputs.checks.checks.checks[0].evidence[0],
    }
    path = tmp_path / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    error = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    with pytest.raises(error):
        data.publish(data.comparison, data.comparison.operation)
    with pytest.raises(error):
        data.load("equivalence", ref, command())


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("change", ["scope", "summary"])
def test_forged_summary_rejected_on_both_boundaries(
    tmp_path: Path, kind: str, change: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    if change == "scope":
        candidate = candidate.model_copy(
            update={"scope": candidate.scope.model_copy(update={"context_id": "other"})}
        )
    elif isinstance(candidate, PublicContextReceipt):
        candidate = candidate.model_copy(update={"equivalence_scope": ("other",)})
    else:
        candidate = candidate.model_copy(update={"status": "rejected"})
    ref = reference(candidate, candidate.schema_version, store=data.store)
    with pytest.raises(OwnershipConflict):
        data.publish(candidate, candidate.operation)
    with pytest.raises(OwnershipConflict):
        data.load(kind, ref, command())


@pytest.mark.parametrize("status", ["fail", "unknown", "missing"])
def test_real_comparison_changes_require_correct_diagnostic_summary(
    tmp_path: Path, status: str
) -> None:
    data = fixture(tmp_path)
    original = data.inputs.checks
    checks = (
        ()
        if status == "missing"
        else tuple(
            c.model_copy(update={"status": status}) for c in original.checks.checks
        )
    )
    facts = original.model_copy(
        update={"checks": StateChecks(required=original.checks.required, checks=checks)}
    )
    facts_ref = reference(facts, facts.schema_version, store=data.store)
    forged = data.comparison.model_copy(update={"checks_ref": facts_ref})
    forged_ref = reference(forged, forged.schema_version, store=data.store)
    with pytest.raises(OwnershipConflict):
        data.publish(forged, forged.operation)
    with pytest.raises(OwnershipConflict):
        data.load("equivalence", forged_ref, command())
    inputs = data.inputs.model_copy(update={"checks": facts, "checks_ref": facts_ref})
    correct = assemble_equivalence(inputs, data.comparison.operation)
    ref = data.publish(correct, correct.operation)
    loaded = data.load("equivalence", ref, command())
    assert isinstance(loaded, EquivalenceReceipt)
    assert loaded.status == ("rejected" if status == "fail" else "unknown")


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize(
    "fault",
    ["run", "owner", "attempt", "new_execute", "parent", "allocation", "recovery"],
)
def test_wrong_publication_scope_rejected_before_authority(
    tmp_path: Path, kind: str, fault: str
) -> None:
    data = fixture(tmp_path)
    candidate = data.candidate(kind)
    original = candidate.operation
    updates: dict[str, dict[str, object]] = {
        "run": {"run_id": "other"},
        "owner": {"owner_id": "other"},
        "attempt": {"attempt_id": "other"},
        "new_execute": {"operation_id": "new"},
        "parent": {
            "operation_id": "new",
            "mode": "cleanup",
            "parent_operation_id": "other",
        },
        "allocation": {
            "operation_id": "new",
            "mode": "cleanup",
            "parent_operation_id": original.operation_id,
            "allocation_id": "other",
        },
        "recovery": {
            "operation_id": "new",
            "mode": "cleanup",
            "parent_operation_id": original.operation_id,
            "recovery_ref": reference({}, "recovery-plan/1"),
        },
    }
    with pytest.raises(OwnershipConflict):
        data.publish(candidate, original.model_copy(update=updates[fault]))
    assert data.authority.calls == []


@pytest.mark.parametrize("kind", ["context", "equivalence"])
@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_invalid_roots_do_not_write(tmp_path: Path, kind: str, bad: object) -> None:
    data = fixture(tmp_path)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(ValidationError):
        if kind == "context":
            data.adapter.publish_context(cast(PublicContextReceipt, bad), command())
        else:
            data.adapter.publish_equivalence(cast(EquivalenceReceipt, bad), command())
    assert set((tmp_path / "blobs").iterdir()) == before
