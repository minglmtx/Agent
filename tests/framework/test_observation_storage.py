"""Real CAS observation transport and shared construction/retrieval input gate."""

from pathlib import Path
from datetime import timedelta
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.observation import (
    Observation,
    ObservationArtifact,
    ObservationCommitUnconfirmed,
    ResolvedObservation,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from observation_fixtures import sample_observation
from test_core_contracts import identity
from test_run_journal import command, CancelSwitch
from test_lifecycle import ManualClock
from test_cpu_retriever import setup as retrieval_setup
from construction_storage_fixtures import fixture as construction_fixture, put
from retrieval_fixtures import reference


def setup(root: Path) -> tuple[FileEvidenceStore, EvidenceObservations, CancelSwitch]:
    store = FileEvidenceStore(root)
    switch = CancelSwitch()
    return (
        store,
        EvidenceObservations(store, OperationGuards(SystemClock(), switch)),
        switch,
    )


def bytes_ref(
    store: FileEvidenceStore, raw: bytes, schema: str = "observation-text/1"
) -> EvidenceRef:
    return store.put(
        raw,
        EvidenceMetadata(
            media_type="text/plain",
            content_schema=schema,
            visibility="public",
            producer="unit-observation",
        ),
    )


@pytest.mark.parametrize("mode", ["inline", "reference", "image"])
def test_publish_repeat_and_load_preserves_content(tmp_path: Path, mode: str) -> None:
    store, adapter, switch = setup(tmp_path)
    observation = sample_observation(identity())
    if mode == "reference":
        observation = observation.model_copy(
            update={"text": None, "text_ref": bytes_ref(store, "中文\r\n".encode())}
        )
    if mode == "image":
        observation = observation.model_copy(
            update={
                "text": None,
                "artifacts": (
                    ObservationArtifact(
                        name="screen",
                        reference=bytes_ref(store, b"unit screenshot", "unit-image/1"),
                    ),
                ),
            }
        )
    op = command(attempt=observation.attempt_id)
    ref = adapter.publish(observation, op)
    assert adapter.publish(observation, op) == ref
    loaded = adapter.load(ref, command())
    assert loaded.record == observation
    assert loaded.text == ("中文\r\n" if mode == "reference" else observation.text)
    assert adapter.load(ref, command(attempt=observation.attempt_id)) == loaded
    assert adapter.load(ref, command(cleanup_parent=op.operation_id)) == loaded
    assert store.read(ref) == observation.model_dump_json().encode()


@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_bad_observation_no_write(tmp_path: Path, bad: object) -> None:
    store, adapter, switch = setup(tmp_path)
    with pytest.raises(ValidationError):
        adapter.publish(cast(Observation, bad), command(attempt="initial-attempt"))
    assert not list((tmp_path / "blobs").iterdir())


@pytest.mark.parametrize("scope", ["run", "wrong", "cleanup"])
def test_publish_requires_matching_attempt_execute(tmp_path: Path, scope: str) -> None:
    store, adapter, switch = setup(tmp_path)
    op = command(attempt="wrong" if scope == "wrong" else None)
    if scope == "cleanup":
        op = command(attempt="initial-attempt", cleanup_parent="parent")
    with pytest.raises(OwnershipConflict):
        adapter.publish(sample_observation(identity()), op)
    assert not list((tmp_path / "blobs").iterdir())


def test_attempt_mismatch_read_and_wrong_schema_rejected(tmp_path: Path) -> None:
    store, adapter, switch = setup(tmp_path)
    ref = adapter.publish(
        sample_observation(identity()), command(attempt="initial-attempt")
    )
    with pytest.raises(OwnershipConflict):
        adapter.load(ref, command(attempt="other"))
    for changes in ({"visibility": "private"}, {"content_schema": "old/1"}):
        with pytest.raises(ValueError):
            adapter.load(ref.model_copy(update=changes), command())


@pytest.mark.parametrize("target", ["record", "text", "artifact"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_actual_dependencies_verified_on_read_and_publish(
    tmp_path: Path, target: str, fault: str
) -> None:
    store, adapter, switch = setup(tmp_path)
    text = bytes_ref(store, b"public text")
    artifact = bytes_ref(store, b"public screenshot", "unit-image/1")
    observation = sample_observation(identity()).model_copy(
        update={
            "text": None,
            "text_ref": text,
            "artifacts": (ObservationArtifact(name="screen", reference=artifact),),
        }
    )
    ref = adapter.publish(observation, command(attempt="initial-attempt"))
    chosen = {"record": ref, "text": text, "artifact": artifact}[target]
    path = tmp_path / "blobs" / chosen.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"changed")
    expected = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    with pytest.raises(expected):
        adapter.load(ref, command())
    if target != "record":
        before = set((tmp_path / "blobs").iterdir())
        with pytest.raises(expected):
            adapter.publish(observation, command(attempt="initial-attempt"))
        assert set((tmp_path / "blobs").iterdir()) == before


def test_invalid_utf8_not_silently_replaced(tmp_path: Path) -> None:
    store, adapter, switch = setup(tmp_path)
    text = bytes_ref(store, b"\xff")
    observation = sample_observation(identity()).model_copy(
        update={"text": None, "text_ref": text}
    )
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(EvidenceIntegrityError) as caught:
        adapter.publish(observation, command(attempt="initial-attempt"))
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
    assert set((tmp_path / "blobs").iterdir()) == before


def test_cancel_after_publication_retains_reference_without_recapture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, adapter, switch = setup(tmp_path)
    observation = sample_observation(identity())
    op = command(attempt=observation.attempt_id).model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    original = store.put

    def cancel(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        result = original(data, metadata)
        switch.cancelled = True
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "put", cancel)
        with pytest.raises(ObservationCommitUnconfirmed) as caught:
            adapter.publish(observation, op)
    assert isinstance(caught.value.__cause__, OperationStopped)
    cleanup = command(cleanup_parent=op.operation_id)
    assert adapter.load(caught.value.reference, cleanup).record == observation
    assert len(list((tmp_path / "blobs").iterdir())) == 1


@pytest.mark.parametrize("after", [False, True])
def test_put_fault_preserves_original_and_exact_existing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after: bool
) -> None:
    store, adapter, switch = setup(tmp_path)
    original = store.put
    error = ExceptionGroup(
        "write and cleanup", [OSError("publish failed"), OSError("close failed")]
    )

    def fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        if after:
            original(data, metadata)
        raise error

    observation = sample_observation(identity())
    with monkeypatch.context() as scoped:
        scoped.setattr(store, "put", fail)
        with pytest.raises(ExceptionGroup) as caught:
            adapter.publish(observation, command(attempt="initial-attempt"))
    assert caught.value is error and len(list((tmp_path / "blobs").iterdir())) == int(
        after
    )
    ref = adapter.publish(observation, command(attempt="initial-attempt"))
    assert adapter.load(ref, command()).record == observation
    assert len(list((tmp_path / "blobs").iterdir())) == 1


@pytest.mark.parametrize(
    "fault",
    ["placeholder", "task", "context", "sequence", "loading", "error", "action_error"],
)
def test_retrieval_rejects_bad_actual_initial_facts_before_encoding(
    tmp_path: Path, fault: str
) -> None:
    h = retrieval_setup(tmp_path)
    observation = sample_observation(h.data.query.task)
    changes: dict[str, dict[str, object]] = {
        "task": {"task": observation.task.model_copy(update={"task_id": "other"})},
        "context": {"context_id": "other"},
        "sequence": {"sequence": 1},
        "loading": {"state": "loading"},
        "error": {"state": "error", "error_code": "NAVIGATION_FAILED"},
        "action_error": {"last_action_error": "Click failed"},
    }
    value: object = (
        {"observation": "old placeholder"}
        if fault == "placeholder"
        else observation.model_copy(update=changes[fault])
    )
    context = h.data.context.model_copy(
        update={
            "initial_observation_ref": reference(
                value, "observation/1", "public", h.store
            )
        }
    )
    query = h.data.query.model_copy(
        update={
            "public_context_ref": reference(
                context, "public-construction-context/1", "public", h.store
            )
        }
    )
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(ValueError):
        h.retriever.retrieve(query, h.data.scope, 6, command())
    assert (
        h.loader.calls == 0 and set((tmp_path / "evidence/blobs").iterdir()) == before
    )


@pytest.mark.parametrize("fault", ["placeholder", "context", "loading"])
def test_construction_rejects_bad_initial_before_snapshot(
    tmp_path: Path, fault: str
) -> None:
    data = construction_fixture(tmp_path)
    context = PublicConstructionContext.model_validate_json(
        data.store.read(data.plan.public_context_ref)
    )
    observation = sample_observation(context.task.identity)
    value: object = (
        {"old": True}
        if fault == "placeholder"
        else observation.model_copy(
            update=(
                {"context_id": "other"} if fault == "context" else {"state": "loading"}
            )
        )
    )
    context = context.model_copy(
        update={
            "initial_observation_ref": put(data.store, value, "observation/1", "public")
        }
    )
    data.plan = data.plan.model_copy(
        update={
            "public_context_ref": put(
                data.store, context, "public-construction-context/1", "public"
            )
        }
    )
    with pytest.raises(ValueError):
        data.journal().create(data.plan, command())
    assert not list((tmp_path / "journal").glob("*.json"))


def test_expiry_during_preflight_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, adapter, switch = setup(tmp_path)
    clock = ManualClock()
    adapter.controls = OperationGuards(clock, switch)
    original = adapter.reader.resolve

    def slow(
        observation: Observation, control: OperationControl
    ) -> ResolvedObservation:
        resolved = original(observation, control)
        clock.sleep(2)
        return resolved

    monkeypatch.setattr(adapter.reader, "resolve", slow)
    op = command(attempt="initial-attempt").model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=1)}
    )
    with pytest.raises(OperationStopped, match="DEADLINE"):
        adapter.publish(sample_observation(identity()), op)
    assert not list((tmp_path / "blobs").iterdir())


def test_cancel_before_publication_has_no_effect(tmp_path: Path) -> None:
    store, adapter, switch = setup(tmp_path)
    switch.cancelled = True
    op = command(attempt="initial-attempt").model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    with pytest.raises(OperationStopped):
        adapter.publish(sample_observation(identity()), op)
    assert not list((tmp_path / "blobs").iterdir())
