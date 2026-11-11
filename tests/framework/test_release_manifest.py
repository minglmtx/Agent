"""Closed role/dependency graph and exact bounded evidence parsing."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.release import ReleaseManifest, ReleaseFile
from lab_generate_skill.adapters.releases.manifest import load_release
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from release_fixtures import manifest, reference


def test_full_role_graph_and_json_reference_roundtrip(tmp_path: Path) -> None:
    expected = manifest(tmp_path / "release")
    raw = expected.model_dump_json().encode()
    assert load_release(raw, reference(raw)) == expected


@pytest.mark.parametrize(
    "fault",
    [
        "missing_role",
        "duplicate_role",
        "wrong_kind",
        "site_scope",
        "global_scope",
        "missing_dependency",
        "cycle",
        "unused_component",
        "duplicate_component",
        "missing_artifact",
        "unused_artifact",
        "overlap",
    ],
)
def test_incomplete_or_ambiguous_graph_rejected(tmp_path: Path, fault: str) -> None:
    data = manifest(tmp_path / "release").model_dump()
    components = list(data["components"])
    roles = list(data["roles"])
    artifacts = list(data["artifacts"])
    if fault == "missing_role":
        roles = [r for r in roles if r["role"] != "teacher"]
    elif fault == "duplicate_role":
        roles.append(roles[0])
    elif fault == "wrong_kind":
        components[0] = {**components[0], "kind": "registry"}
    elif fault == "site_scope":
        roles = [
            {**r, "scope_id": "other"} if r["role"] == "evaluator" else r for r in roles
        ]
    elif fault == "global_scope":
        roles = [
            {**r, "scope_id": "other"} if r["role"] == "teacher" else r for r in roles
        ]
    elif fault == "missing_dependency":
        components[0] = {**components[0], "dependencies": ("missing",)}
    elif fault == "cycle":
        components = [
            {**c, "dependencies": ("teacher",)} if c["component_id"] == "code" else c
            for c in components
        ]
    elif fault == "unused_component":
        components.append({**components[0], "component_id": "unused"})
    elif fault == "duplicate_component":
        components.append(components[0])
    elif fault == "missing_artifact":
        components[0] = {**components[0], "artifact_ids": ("missing",)}
    elif fault == "unused_artifact":
        artifacts.append(
            {**artifacts[0], "artifact_id": "unused", "root": str(tmp_path / "unused")}
        )
    else:
        artifacts.append(
            {
                **artifacts[0],
                "artifact_id": "nested",
                "root": str(tmp_path / "release/nested"),
            }
        )
    with pytest.raises(ValidationError):
        ReleaseManifest.model_validate(
            {
                **data,
                "components": tuple(components),
                "roles": tuple(roles),
                "artifacts": tuple(artifacts),
            }
        )


@pytest.mark.parametrize(
    "path",
    ["", ".", "../outside", "/absolute", "a/../b", "a//b", "./a", "a\\b", "a\0b"],
)
def test_noncanonical_file_path_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        ReleaseFile(path=path, sha256="a" * 64, size_bytes=0, executable=False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_bytes", True),
        ("size_bytes", -1),
        ("size_bytes", "0"),
        ("executable", 1),
        ("sha256", "bad"),
    ],
)
def test_strict_file_metadata(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ReleaseFile.model_validate(
            {
                "path": "file",
                "sha256": "a" * 64,
                "size_bytes": 0,
                "executable": False,
                field: value,
            }
        )


@pytest.mark.parametrize(
    "raw",
    [b"", b"[]", b'{"release_id":"one","release_id":"two"}', b'{"value":NaN}', b"\xff"],
)
def test_bad_manifest_evidence_rejected(raw: bytes) -> None:
    with pytest.raises(EvidenceIntegrityError):
        load_release(raw, reference(raw))


def test_reference_mismatch_and_directory_file_collision(tmp_path: Path) -> None:
    expected = manifest(tmp_path / "release")
    raw = expected.model_dump_json().encode()
    with pytest.raises(EvidenceIntegrityError):
        load_release(raw + b" ", reference(raw))
    data = expected.model_dump()
    artifact = data["artifacts"][0]
    bad = {**artifact["files"][0], "path": "bin"}
    with pytest.raises(ValidationError):
        ReleaseManifest.model_validate(
            {**data, "artifacts": ({**artifact, "files": (*artifact["files"], bad)},)}
        )
