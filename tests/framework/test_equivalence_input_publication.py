"""Complete original producer bodies to publisher/readback, no graph rebuild or actions."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.public_context import ContextCommitUnconfirmed
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    assemble_equivalence,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from context_storage_fixtures import fixture
from retrieval_fixtures import reference


def test_verified_equivalence_consumes_complete_inputs_once_and_rechecks_live_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    reads = []
    original = data.store.read

    def read(ref: Any, control: Any = None) -> bytes:
        reads.append(ref)
        return original(ref, control)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Already handed producer graph was rebuilt")

    monkeypatch.setattr(data.store, "read", read)
    monkeypatch.setattr(data.adapter.facts, "context", forbidden)
    monkeypatch.setattr(data.adapter.facts, "equivalence", forbidden)
    data.authority.calls.clear()
    ref = data.adapter.publish_equivalence_verified(
        data.comparison, data.inputs, data.comparison.operation
    )
    assert original(ref) == data.comparison.model_dump_json().encode()
    assert (
        data.authority.calls
        == ["baseline", "reset", "context", "baseline", "equivalence"] * 2
    )
    assert reads.count(data.inputs.checks.checks.checks[0].evidence[0]) == 1
    assert reads.count(ref) == 1
    # A separate invocation gets a fresh dependency read and all authority gates.
    assert (
        data.adapter.publish_equivalence_verified(
            data.comparison, data.inputs, data.comparison.operation
        )
        == ref
    )
    assert reads.count(data.inputs.checks.checks.checks[0].evidence[0]) == 2


@pytest.mark.parametrize(
    "fault", ["source-ref", "candidate-body", "checks-ref", "source-body"]
)
def test_wrong_or_missing_handoff_refuses_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    d = fixture(tmp_path)
    inputs = d.inputs
    if fault == "source-ref":
        inputs = inputs.model_copy(update={"source_ref": inputs.candidate_ref})
    elif fault == "candidate-body":
        value = inputs.candidate_inputs
        value = value.model_copy(
            update={
                "observation": value.observation.model_copy(
                    update={"last_action_error": "different"}
                )
            }
        )
        inputs = inputs.model_copy(update={"candidate_inputs": value})
    elif fault == "checks-ref":
        inputs = inputs.model_copy(
            update={
                "checks_ref": inputs.checks_ref.model_copy(update={"sha256": "0" * 64})
            }
        )
    else:
        value = inputs.source_inputs.baseline_inputs
        value = value.model_copy(
            update={
                "observation": value.observation.model_copy(
                    update={"last_action_error": "different"}
                )
            }
        )
        source = inputs.source_inputs.model_copy(update={"baseline_inputs": value})
        inputs = inputs.model_copy(update={"source_inputs": source})
    writes = []

    def no_write(*args: Any, **kwargs: Any) -> Any:
        writes.append(1)
        pytest.fail("Invalid body published")

    monkeypatch.setattr(d.store, "put", no_write)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        d.adapter.publish_equivalence_verified(
            d.comparison, inputs, d.comparison.operation
        )
    assert not writes


@pytest.mark.parametrize("gate", ["denied_context", "denied", "denied_equivalence"])
def test_verified_publication_never_caches_current_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    d = fixture(tmp_path)
    setattr(d.authority, gate, True)
    writes = []

    def no_write(*args: Any, **kwargs: Any) -> Any:
        writes.append(1)
        pytest.fail("Revoked source/state/compare authority published")

    monkeypatch.setattr(d.store, "put", no_write)
    with pytest.raises(OwnershipConflict):
        d.adapter.publish_equivalence_verified(
            d.comparison, d.inputs, d.comparison.operation
        )
    assert not writes


@pytest.mark.parametrize("when", ["before", "after-commit"])
def test_source_reset_gate_is_checked_before_publication_and_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    d = fixture(tmp_path)
    original_put = d.store.put
    reset_check = d.authority.verify_reset
    denied = when == "before"
    committed = []

    def verify_reset(*args: Any, **kwargs: Any) -> None:
        if denied:
            raise OwnershipConflict("Original source Reset authority revoked")
        reset_check(*args, **kwargs)

    def put(raw: bytes, metadata: Any, control: Any = None, **kwargs: Any) -> Any:
        nonlocal denied
        ref = original_put(raw, metadata, control, **kwargs)
        if metadata.content_schema == "equivalence-receipt/1":
            committed.append(ref)
            denied = True
        return ref

    monkeypatch.setattr(d.authority, "verify_reset", verify_reset)
    monkeypatch.setattr(d.store, "put", put)
    with pytest.raises(
        OwnershipConflict if when == "before" else ContextCommitUnconfirmed
    ) as caught:
        d.adapter.publish_equivalence_verified(
            d.comparison, d.inputs, d.comparison.operation
        )
    if when == "before":
        assert not committed
    else:
        assert isinstance(caught.value, ContextCommitUnconfirmed)
        assert committed == [caught.value.reference]
        assert isinstance(caught.value.__cause__, OwnershipConflict)


def test_revocation_after_commit_retains_reference_without_source_or_action_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = fixture(tmp_path)
    put = d.store.put
    committed = []

    def revoked(raw: bytes, metadata: Any, control: Any = None, **kwargs: Any) -> Any:
        ref = put(raw, metadata, control, **kwargs)
        if metadata.content_schema == "equivalence-receipt/1":
            committed.append(ref)
            d.authority.denied_context = True
        return ref

    monkeypatch.setattr(d.store, "put", revoked)
    with pytest.raises(ContextCommitUnconfirmed) as caught:
        d.adapter.publish_equivalence_verified(
            d.comparison, d.inputs, d.comparison.operation
        )
    assert committed == [caught.value.reference]
    assert isinstance(caught.value.__cause__, OwnershipConflict)
    assert (
        d.store.read(caught.value.reference) == d.comparison.model_dump_json().encode()
    )


@pytest.mark.parametrize("when", ["before", "readback"])
def test_cancel_before_or_after_commit_preserves_original_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    d = fixture(tmp_path)
    put = d.store.put
    committed = []
    op = d.comparison.operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="equivalence-cancel", run_id="run", owner_id="owner"
            )
        }
    )
    comparison = assemble_equivalence(d.inputs, op)
    if when == "before":
        d.switch.cancelled = True

    def cancel(raw: bytes, metadata: Any, control: Any = None, **kwargs: Any) -> Any:
        ref = put(raw, metadata, control, **kwargs)
        if metadata.content_schema == "equivalence-receipt/1":
            committed.append(ref)
            d.switch.cancelled = True
        return ref

    monkeypatch.setattr(d.store, "put", cancel)
    with pytest.raises(
        OperationStopped if when == "before" else ContextCommitUnconfirmed
    ):
        d.adapter.publish_equivalence_verified(comparison, d.inputs, op)
    assert len(committed) == (0 if when == "before" else 1)


def test_negative_comparison_is_preserved_and_cannot_be_relabelled_equivalent(
    tmp_path: Path,
) -> None:
    d = fixture(tmp_path)
    inputs = d.inputs
    facts = inputs.checks
    failed = facts.checks.model_copy(
        update={
            "checks": tuple(
                c.model_copy(
                    update={"status": "fail", "reason_code": "ACTUAL_CONTENTS_DIFFER"}
                )
                for c in facts.checks.checks
            )
        }
    )
    facts = facts.model_copy(update={"checks": failed})
    ref = reference(facts, facts.schema_version, store=d.store)
    inputs = inputs.model_copy(update={"checks": facts, "checks_ref": ref})
    rejected = assemble_equivalence(inputs, d.comparison.operation)
    assert rejected.status == "rejected"
    saved = d.adapter.publish_equivalence_verified(rejected, inputs, rejected.operation)
    assert d.store.read(saved) == rejected.model_dump_json().encode()
    with pytest.raises(OwnershipConflict):
        d.adapter.publish_equivalence_verified(
            rejected.model_copy(update={"status": "equivalent"}),
            inputs,
            rejected.operation,
        )
