"""Reject corrupt registry bytes and release binding mismatches before imports."""

from pathlib import Path

import pytest

from lab_generate_skill.adapters.releases.registry_manifest import load_registry
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.registry.resolve import TaskRegistry
from registry_fixtures import fixture


@pytest.mark.parametrize(
    "raw",
    [b"", b"null", b"[]", b"{}", b"\xff", b'{"x":NaN}', b"x" * (8 * 1024 * 1024 + 1)],
)
def test_malformed_or_oversized_registry(raw: bytes) -> None:
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="task-registry/1",
            visibility="private",
            producer="unit",
        ),
    )
    with pytest.raises(EvidenceIntegrityError):
        load_registry(raw, ref)


@pytest.mark.parametrize("fault", ["sha", "size", "visibility", "schema"])
def test_registry_reference_mismatch(tmp_path: Path, fault: str) -> None:
    f = fixture(tmp_path)
    changes: dict[str, dict[str, object]] = {
        "sha": {"sha256": "f" * 64},
        "size": {"size_bytes": f.reference.size_bytes + 1},
        "visibility": {"visibility": "public"},
        "schema": {"content_schema": "other/1"},
    }
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        load_registry(
            f.index.model_dump_json().encode(),
            f.reference.model_copy(update=changes[fault]),
        )


@pytest.mark.parametrize(
    "fault",
    ["registry_file", "source_file", "interface", "minor", "supported_duplicate"],
)
def test_actual_release_pins_are_checked(tmp_path: Path, fault: str) -> None:
    f = fixture(tmp_path)
    data = f.release.model_dump()
    if fault in ("registry_file", "source_file"):
        path = (
            "registry.json"
            if fault == "registry_file"
            else f.index.components[0].implementation.path
        )
        data["artifacts"][0]["files"] = tuple(
            {**item, "sha256": "f" * 64} if item["path"] == path else item
            for item in data["artifacts"][0]["files"]
        )
    elif fault in ("interface", "minor"):
        field, value = (
            ("interface_id", "changed")
            if fault == "interface"
            else ("contract_version", "1.1")
        )
        data["components"] = tuple(
            {**c, field: value} if c["component_id"] == "collector" else c
            for c in data["components"]
        )
    release = ReleaseManifest.model_validate(data)
    supported = (
        f.supported + f.supported[:1] if fault == "supported_duplicate" else f.supported
    )
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        TaskRegistry(f.index, f.reference, release, supported)
