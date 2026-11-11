"""Bounded immutable body transport and real write confirmation, without native work."""

from collections import Counter
from dataclasses import FrozenInstanceError
from typing import Any, cast
import pytest
from lab_generate_skill.application.actor_context_review_inputs import (
    ActorContextReviewInputs,
)
from lab_generate_skill.application.actor_context_preparation_inputs import (
    ActorContextPreparationInputs,
)
from lab_generate_skill.application.verified_evidence_inputs import (
    verified_input_bytes,
    verified_input_document,
)
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.lifecycle import OperationControl


class Guard:
    cancelled = False
    checks = 0

    def checkpoint(self) -> float:
        self.checks += 1
        if self.cancelled:
            raise OperationStopped("CANCELLED", "verified-actor-input")
        return 60

    def wait(self, seconds: float) -> None:
        self.checkpoint()


class Store:
    """Explicit transport double; missing/false write acknowledgments remain visible."""

    def __init__(self) -> None:
        self.values: dict[EvidenceRef, bytes] = {}
        self.reads: Counter[EvidenceRef] = Counter()
        self.write_fault = "none"

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        self.reads[ref] += 1
        return self.values[ref]

    def put(
        self, raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        ref = evidence_reference(raw, metadata)
        if self.write_fault == "missing":
            self.values.pop(ref, None)
        else:
            self.values[ref] = raw if self.write_fault != "body" else raw + b" "
        if self.write_fault == "partial":
            raise OSError("Original write lost its acknowledgment")
        if self.write_fault == "identity":
            return ref.model_copy(update={"producer": "foreign"})
        return ref


def metadata(schema: str = "model-parameters/1") -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="unit-verified-input",
    )


def sample() -> bytes:
    return (
        LocalActorParameters(
            max_input_tokens=32, max_new_tokens=8, seed=0, temperature=0.0, top_p=1.0
        )
        .model_dump_json()
        .encode()
    )


def test_complete_value_checked_once_and_cached_document_is_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, control = Store(), Guard()
    raw = sample()
    ref = store.put(raw, metadata(), control)
    inputs = ActorContextReviewInputs(store)
    first = verified_input_document(inputs, ref, LocalActorParameters, 16384, control)
    body = inputs.read_verified(ref, control)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(body, "raw", b"changed")
    with pytest.raises(TypeError):
        cast(Any, inputs.bodies)[ref] = raw + b" "

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Already verified immutable body was hashed or parsed again")

    import hashlib

    monkeypatch.setattr(hashlib, "sha256", forbidden)
    monkeypatch.setattr(LocalActorParameters, "model_validate_json", forbidden)
    assert (
        verified_input_document(inputs, ref, LocalActorParameters, 16384, control)
        is first
    )
    assert verified_input_bytes(inputs, ref, 16384, control) is body.raw
    assert store.reads[ref] == 1
    assert control.checks > 3
    control.cancelled = True
    with pytest.raises(OperationStopped):
        inputs.read(ref, control)
    control.cancelled = False
    inputs.clear()
    assert not inputs.bodies
    with pytest.raises(OwnershipConflict):
        inputs.read(ref, control)


@pytest.mark.parametrize("fault", ["body", "size", "mutable"])
def test_invalid_complete_body_never_enters_graph(fault: str) -> None:
    raw, store, control = sample(), Store(), Guard()
    ref = store.put(raw, metadata(), control)
    bad: Any = raw
    if fault == "body":
        bad += b" "
    elif fault == "size":
        ref = ref.model_copy(update={"size_bytes": len(raw) + 1})
    else:
        bad = bytearray(raw)
    with pytest.raises(EvidenceIntegrityError):
        VerifiedEvidenceBody(ref, bad)


@pytest.mark.parametrize(
    "field,value",
    [("producer", "foreign"), ("visibility", "public"), ("uri", "cas://foreign")],
)
def test_same_digest_does_not_alias_complete_reference(field: str, value: str) -> None:
    store, control = Store(), Guard()
    ref = store.put(sample(), metadata(), control)
    inputs = ActorContextReviewInputs(store)
    inputs.read(ref, control)
    foreign = ref.model_copy(update={field: value})
    with pytest.raises(KeyError):
        inputs.read(foreign, control)
    assert store.reads[foreign] == 1 and len(inputs.bodies) == 1


@pytest.mark.parametrize("fault", ["none", "missing", "body", "identity", "partial"])
def test_publication_always_reads_original_store_even_when_body_is_retained(
    fault: str,
) -> None:
    store, control = Store(), Guard()
    inputs = ActorContextPreparationInputs(store)
    raw = sample()
    ref = inputs.put(raw, metadata(), control)
    assert store.reads[ref] == 1
    store.write_fault = fault
    if fault == "none":
        assert inputs.put(raw, metadata(), control) == ref
        assert store.reads[ref] == 2
        assert inputs.read(ref, control) == raw
        assert store.reads[ref] == 2
    else:
        with pytest.raises((KeyError, EvidenceIntegrityError, OSError)):
            inputs.put(raw, metadata(), control)
        assert store.reads[ref] == (2 if fault in ("missing", "body") else 1)


def test_count_and_declared_byte_limits_refuse_before_original_io() -> None:
    store, control = Store(), Guard()
    inputs = ActorContextReviewInputs(store)
    for i in range(32):
        ref = store.put(str(i).encode(), metadata(), control)
        inputs.read(ref, control)
    extra = store.put(b"extra", metadata(), control)
    with pytest.raises(EvidenceIntegrityError):
        inputs.read(extra, control)
    assert store.reads[extra] == 0
    inputs = ActorContextReviewInputs(store)
    large = extra.model_copy(update={"size_bytes": 16 * 1024**2 + 1})
    with pytest.raises(EvidenceIntegrityError):
        inputs.read(large, control)
    assert store.reads[large] == 0


def test_aggregate_bound_is_shared_by_all_retained_members() -> None:
    store, control = Store(), Guard()
    inputs = ActorContextReviewInputs(store)
    for i in range(4):
        ref = store.put(bytes([i]) * (16 * 1024**2), metadata(), control)
        inputs.read(ref, control)
    extra = store.put(b"x", metadata(), control)
    with pytest.raises(EvidenceIntegrityError):
        inputs.read(extra, control)
    assert store.reads[extra] == 0


@pytest.mark.parametrize("canonical", [False, True])
def test_canonical_requirement_has_a_separate_cache_identity(canonical: bool) -> None:
    store, control = Store(), Guard()
    raw = sample() + b"\n"
    ref = store.put(raw, metadata(), control)
    inputs = ActorContextReviewInputs(store)
    assert inputs.read_document(
        ref, LocalActorParameters, 16384, control, canonical=False
    )
    if canonical:
        with pytest.raises(EvidenceIntegrityError):
            verified_input_document(inputs, ref, LocalActorParameters, 16384, control)
    else:
        assert verified_input_document(
            inputs, ref, LocalActorParameters, 16384, control, canonical=False
        )
    assert store.reads[ref] == 1


def test_unapproved_mutable_models_are_parsed_afresh_and_foreign_schemas_not_retained() -> (
    None
):
    class Mutable(Contract):
        facts: dict[str, int]

    store, control = Store(), Guard()
    raw = Mutable(facts={"original": 1}).model_dump_json().encode()
    ref = store.put(raw, metadata(), control)
    inputs = ActorContextReviewInputs(store)
    first = verified_input_document(inputs, ref, Mutable, 1024, control)
    first.facts["original"] = 2
    assert verified_input_document(inputs, ref, Mutable, 1024, control).facts == {
        "original": 1
    }
    other = store.put(raw, metadata("foreign/1"), control)
    assert inputs.read(other, control) == inputs.read(other, control)
    assert store.reads[other] == 2 and other not in inputs.bodies
