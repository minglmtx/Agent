"""Immutable bodies reused only by one original closed-proof reader instance."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceError, OperationStopped


def data(root: Path) -> tuple[Any, Any]:
    store = FileEvidenceStore(root)
    meta = EvidenceMetadata(
        media_type="text/plain",
        content_schema="unit-body/1",
        visibility="private",
        producer="unit-body",
    )
    return store, store.put(b"immutable-body", meta)


def test_exact_body_once_within_proof_but_new_proof_rereads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ref = data(tmp_path)
    reader = ReadOnlyEvidence(tmp_path, max_object_bytes=64, reuse_within_proof=True)
    calls = []
    original = reader.store.read

    def count(*a: Any, **k: Any) -> Any:
        calls.append(a)
        return original(*a, **k)

    monkeypatch.setattr(reader.store, "read", count)
    control = SimpleNamespace(checkpoint=lambda: 60)
    assert reader.read(ref, control) == reader.read(ref, control) == b"immutable-body"
    assert len(calls) == reader.body_read_count == 1 and reader.read_count == 2
    fresh = ReadOnlyEvidence(tmp_path, max_object_bytes=64, reuse_within_proof=True)
    assert fresh.read(ref, control) == b"immutable-body" and fresh.body_read_count == 1
    (tmp_path / "blobs" / ref.sha256).unlink()
    fresh = ReadOnlyEvidence(tmp_path, max_object_bytes=64, reuse_within_proof=True)
    with pytest.raises(EvidenceError):
        fresh.read(ref, control)


def test_cached_body_still_obeys_control_and_exact_reference_key(
    tmp_path: Path,
) -> None:
    _, ref = data(tmp_path)
    r = ReadOnlyEvidence(tmp_path, max_object_bytes=64, reuse_within_proof=True)
    allowed = SimpleNamespace(checkpoint=lambda: 60)
    assert r.read(ref, allowed)

    def denied() -> float:
        raise OperationStopped("CANCELLED", "proof")

    with pytest.raises(OperationStopped):
        r.read(ref, SimpleNamespace(checkpoint=denied))
    assert r.body_read_count == r.read_count == 1
    other = ref.model_copy(update={"producer": "another-declaration"})
    # Raw body capability never grants either producer identity. The semantic
    # caller still checks it; full Reference keys remain distinct here.
    assert r.read(other, allowed) == b"immutable-body" and r.body_read_count == 2


def test_default_read_and_bounded_reuse_preserve_original_reads(tmp_path: Path) -> None:
    store, ref = data(tmp_path)
    control = SimpleNamespace(checkpoint=lambda: 60)
    r = ReadOnlyEvidence(tmp_path, max_object_bytes=64)
    assert r.read(ref, control) == r.read(ref, control) and r.body_read_count == 2
    second = store.put(
        b"another-body",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="unit-body/1",
            visibility="private",
            producer="unit-body",
        ),
    )
    bounded = ReadOnlyEvidence(tmp_path, max_object_bytes=16, reuse_within_proof=True)
    bounded.read(ref, control)
    bounded.read(second, control)
    bounded.read(second, control)
    assert bounded._body_bytes <= 16 and bounded.body_read_count == 3


@pytest.mark.parametrize("bad", [None, 0, 1, "true", [], {}])
def test_invalid_reuse_flag_does_not_initialize_storage(
    tmp_path: Path, bad: Any
) -> None:
    root = tmp_path / "never"
    with pytest.raises(TypeError):
        ReadOnlyEvidence(root, max_object_bytes=64, reuse_within_proof=bad)
    assert not root.exists()
