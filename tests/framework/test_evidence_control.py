"""Explicit control reaches the storage port, not only before/after a helper."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.generator_execution_evidence import read_exact
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.models.local_generator_evidence import (
    LocalGeneratorEvidence,
    local_metadata,
)
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl


class ObservedStore:
    def __init__(self, root: Path, expected: OperationControl) -> None:
        self.primitive = FileEvidenceStore(root)
        self.expected = expected
        self.calls = 0

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        assert control is self.expected
        control.checkpoint()
        self.calls += 1
        return self.primitive.read(reference)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        assert control is self.expected
        control.checkpoint()
        self.calls += 1
        return self.primitive.put(data, metadata)


@pytest.mark.parametrize("consumer", ["exact", "state", "local"])
def test_original_control_reaches_reader(tmp_path: Path, consumer: str) -> None:
    control = DeadlineControl(5, "original-control")
    store = ObservedStore(tmp_path, control)
    ref = store.primitive.put(b"original", local_metadata("control-test/1"))
    if consumer == "exact":
        assert read_exact(store, ref, 128, control) == b"original"
    elif consumer == "state":
        assert StateReads(store).read(ref, control) == b"original"
    else:
        assert LocalGeneratorEvidence(store).read(ref, 128, control) == b"original"
    assert store.calls == 1


def test_original_control_reaches_writer(tmp_path: Path) -> None:
    control = DeadlineControl(5, "original-control")
    store = ObservedStore(tmp_path, control)
    ref = LocalGeneratorEvidence(store).put(b"original", "control-test/1", control)
    assert store.primitive.read(ref) == b"original" and store.calls == 2


@pytest.mark.parametrize("consumer", ["exact", "state", "local", "write"])
def test_expired_original_control_prevents_storage_effect(
    tmp_path: Path, consumer: str
) -> None:
    control = DeadlineControl(5, "expired-original")
    store = ObservedStore(tmp_path, control)
    ref = store.primitive.put(b"original", local_metadata("control-test/1"))
    control._expires = -1
    with pytest.raises(OperationStopped):
        if consumer == "exact":
            read_exact(store, ref, 128, control)
        elif consumer == "state":
            StateReads(store).read(ref, control)
        elif consumer == "local":
            LocalGeneratorEvidence(store).read(ref, 128, control)
        else:
            LocalGeneratorEvidence(store).put(b"new", "control-test/1", control)
    assert store.calls == 0 and len(list(store.primitive._blobs.iterdir())) == 1


@pytest.mark.parametrize("consumer", ["exact", "state", "local"])
def test_stop_during_read_does_not_return_evidence(
    tmp_path: Path, consumer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = DeadlineControl(5, "cancel-during-read")
    store = ObservedStore(tmp_path, control)
    ref = store.primitive.put(b"original", local_metadata("control-test/1"))
    original = store.read

    def read(reference: EvidenceRef, control: OperationControl) -> bytes:
        value = original(reference, control)
        store.expected._expires = -1  # type: ignore[attr-defined]
        return value

    monkeypatch.setattr(store, "read", read)
    with pytest.raises(OperationStopped):
        if consumer == "exact":
            read_exact(store, ref, 128, control)
        elif consumer == "state":
            StateReads(store).read(ref, control)
        else:
            LocalGeneratorEvidence(store).read(ref, 128, control)
    assert store.calls == 1


@pytest.mark.parametrize("kind", ["reader", "store", "evaluator"])
def test_current_ports_cannot_omit_control(kind: str) -> None:
    from inspect import signature
    from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
    from lab_generate_skill.ports.evaluator import Evaluator

    # These are declaration checks, not a claim of a concrete website evaluator.
    contract, args = {
        "reader": (signature(EvidenceReader.read), (object(), object())),
        "store": (signature(EvidenceStore.put), (object(), b"data", object())),
        "evaluator": (signature(Evaluator.evaluate), (object(), object(), object())),
    }[kind]
    with pytest.raises(TypeError, match="control"):
        contract.bind(*args)
    control = DeadlineControl(5, "port-control")
    assert contract.bind(*args, control=control).arguments["control"] is control
