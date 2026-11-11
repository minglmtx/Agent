"""Exercise real filesystem integrity, concurrent persistence and safe lookup."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest

from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef


def metadata() -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema="capture/1",
        visibility="private",
        producer="capture-1",
    )


def test_round_trip_through_worker_primitive(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b'{"native": true}', metadata())
    assert (
        store.read(EvidenceRef.model_validate_json(ref.model_dump_json()))
        == b'{"native": true}'
    )
    assert store.put(b'{"native": true}', metadata()) == ref
    assert len(list((tmp_path / "blobs").iterdir())) == 1


def test_concurrent_writers_publish_one_complete_object(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    payload = b"captured\x00bytes" * 1000
    with ThreadPoolExecutor(max_workers=8) as executor:
        refs = list(executor.map(lambda _: store.put(payload, metadata()), range(24)))
    assert all(ref == refs[0] for ref in refs)
    assert store.read(refs[0]) == payload
    assert len(list((tmp_path / "blobs").iterdir())) == 1


def test_corruption_is_rejected_and_never_overwritten(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b"good", metadata())
    path = tmp_path / "blobs" / ref.sha256
    path.write_bytes(b"evil")
    with pytest.raises(EvidenceIntegrityError):
        store.read(ref)
    with pytest.raises(EvidenceIntegrityError):
        store.put(b"good", metadata())
    assert path.read_bytes() == b"evil"
    assert not list((tmp_path / "blobs").glob(".pending-*"))


def test_missing_object_has_distinct_diagnostic(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b"capture", metadata())
    (tmp_path / "blobs" / ref.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        store.read(ref)


@pytest.mark.parametrize(
    "field,value", [("uri", "file:///etc/passwd"), ("size_bytes", 100)]
)
def test_reference_cannot_redirect_or_misstate_size(
    tmp_path: Path, field: str, value: object
) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b"capture", metadata())
    data = ref.model_dump()
    data[field] = value
    with pytest.raises(EvidenceIntegrityError):
        store.read(EvidenceRef.model_validate(data))


def test_symlink_object_is_not_followed(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b"capture", metadata())
    blob = tmp_path / "blobs" / ref.sha256
    blob.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"capture")
    blob.symlink_to(outside)
    with pytest.raises(EvidenceIntegrityError):
        store.read(ref)
    with pytest.raises(EvidenceIntegrityError):
        store.put(b"capture", metadata())


def test_object_limit_rejects_without_truncation(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path, max_object_bytes=4)
    ref = store.put(b"good", metadata())
    with pytest.raises(EvidenceIntegrityError):
        store.put(b"too large", metadata())
    (tmp_path / "blobs" / ref.sha256).write_bytes(b"grown object")
    with pytest.raises(EvidenceIntegrityError):
        store.read(ref)


def test_empty_object_round_trip(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    ref = store.put(b"", metadata())
    assert store.read(ref) == b""


@pytest.mark.parametrize("initialize", [None, 0, 1, "false", []])
def test_initialization_flag_validated_before_effects(
    tmp_path: Path, initialize: object
) -> None:
    with pytest.raises(TypeError):
        FileEvidenceStore(tmp_path, initialize=cast(bool, initialize))
    assert list(tmp_path.iterdir()) == []
