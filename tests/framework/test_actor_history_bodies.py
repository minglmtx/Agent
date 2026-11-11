"""Retain exact history within one input lifetime, preserve long legal streams."""

import pytest
from lab_generate_skill.application.actor_context_review_inputs import (
    ActorContextReviewInputs,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from test_verified_actor_inputs import Store, Guard, metadata


@pytest.mark.parametrize("schema", ["actor-model-response/1", "actor-parse-failure/1"])
def test_exact_history_is_read_once_but_current_cancel_and_clear_still_apply(
    schema: str,
) -> None:
    store, control = Store(), Guard()
    ref = store.put(b'{"original":"history"}', metadata(schema), control)
    inputs = ActorContextReviewInputs(store)
    assert inputs.read(ref, control) == inputs.read(ref, control)
    assert store.reads[ref] == 1 and not inputs.bodies
    control.cancelled = True
    with pytest.raises(OperationStopped):
        inputs.read(ref, control)
    control.cancelled = False
    inputs.clear()
    with pytest.raises(OwnershipConflict):
        inputs.read(ref, control)
    assert store.reads[ref] == 1
    assert ActorContextReviewInputs(store).read(ref, control) == store.values[ref]
    assert store.reads[ref] == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("producer", "changed"),
        ("visibility", "public"),
        ("uri", "cas://other"),
        ("content_schema", "actor-parse-failure/1"),
    ],
)
def test_history_never_aliases_full_reference(field: str, value: str) -> None:
    store, control = Store(), Guard()
    ref = store.put(b"history", metadata("actor-model-response/1"), control)
    inputs = ActorContextReviewInputs(store)
    inputs.read(ref, control)
    foreign = ref.model_copy(update={field: value})
    with pytest.raises(KeyError):
        inputs.read(foreign, control)
    assert store.reads[foreign] == 1


@pytest.mark.parametrize("fault", ["bytes", "size"])
def test_corrupt_history_is_not_retained(fault: str) -> None:
    store, control = Store(), Guard()
    ref = store.put(b"history", metadata("actor-model-response/1"), control)
    if fault == "bytes":
        store.values[ref] = b"wrong"
    else:
        ref = ref.model_copy(update={"size_bytes": ref.size_bytes + 1})
        store.values[ref] = b"history"
    inputs = ActorContextReviewInputs(store)
    with pytest.raises(EvidenceIntegrityError):
        inputs.read(ref, control)
    assert store.reads[ref] == 1


def test_long_history_streams_without_expanding_or_exhausting_primary_32_objects() -> (
    None
):
    store, control = Store(), Guard()
    inputs = ActorContextReviewInputs(store)
    primary = [store.put(str(i).encode(), metadata(), control) for i in range(32)]
    for ref in primary:
        inputs.read(ref, control)
    history = [
        store.put(str(i).encode(), metadata("actor-model-response/1"), control)
        for i in range(100)
    ]
    for ref in history:
        assert inputs.read(ref, control) == store.values[ref]
    assert len(inputs.bodies) == 32
    assert inputs.read(history[-1], control) == store.values[history[-1]]
    assert store.reads[history[-1]] == 1
    # Eviction causes a lawful reread, never loss of history or extra send.
    assert inputs.read(history[0], control) == store.values[history[0]]
    assert store.reads[history[0]] == 2
    extra = store.put(b"primary-overflow", metadata(), control)
    with pytest.raises(EvidenceIntegrityError):
        inputs.read(extra, control)
    assert store.reads[extra] == 0


def test_optional_history_yields_to_primary_and_keeps_original_64mib_total() -> None:
    store, control = Store(), Guard()
    inputs = ActorContextReviewInputs(store)
    history = store.put(
        b"h" * (8 * 1024**2), metadata("actor-model-response/1"), control
    )
    inputs.read(history, control)
    for i in range(4):
        ref = store.put(bytes([i]) * (16 * 1024**2), metadata(), control)
        inputs.read(ref, control)
    assert sum(map(len, inputs.bodies.values())) == 64 * 1024**2
    assert inputs.read(history, control) == store.values[history]
    assert inputs.read(history, control) == store.values[history]
    assert store.reads[history] == 3  # Streamed while primary holds the full bound.
    inputs.clear()


def test_large_legal_history_body_streams_without_becoming_a_new_admission_limit() -> (
    None
):
    store, control = Store(), Guard()
    ref = store.put(
        b"h" * (8 * 1024**2 + 1), metadata("actor-model-response/1"), control
    )
    inputs = ActorContextReviewInputs(store)
    assert inputs.read(ref, control) == inputs.read(ref, control)
    assert store.reads[ref] == 2
