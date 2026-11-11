"""Real immutable files/CAS for release admission; no inference or live rights."""

import json
import shutil
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_release import (
    verify_actor_release,
)
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_resource_fixtures import ResourceCase, resource_case
from actor_release_fixtures import metadata


@pytest.fixture
def c(tmp_path: Path) -> ResourceCase:
    return resource_case(tmp_path, Path("/not-launched/python"))


def binding(c: ResourceCase) -> ActorModelBinding:
    return ActorModelBinding.model_validate_json(
        c.evidence.read(c.spec.model_binding_ref)
    )


def verify(c: ResourceCase) -> None:
    verify_actor_release(c.spec, c.evidence, c.workspace_root, c.controls.bind(c.op))


def replace_binding(c: ResourceCase, value: ActorModelBinding) -> None:
    ref = c.evidence.put(value.model_dump_json().encode(), metadata("model-binding/1"))
    c.spec = c.spec.model_copy(update={"model_binding_ref": ref})


def replace_manifest(c: ResourceCase, value: ReleaseManifest) -> None:
    ref = c.evidence.put(
        value.model_dump_json().encode(), metadata("release-manifest/1")
    )
    replace_binding(c, binding(c).model_copy(update={"release_ref": ref}))
    c.spec = c.spec.model_copy(update={"release_ref": ref})


def no_resource_effects(c: ResourceCase) -> None:
    assert not tuple(c.journal._root.iterdir())
    assert not c.authority.workers and not c.authority.closed


def test_actual_release_config_and_model_are_exact_and_read_only(
    c: ResourceCase,
) -> None:
    before = {
        p: p.read_bytes() for p in (c.workspace_root / "evidence/blobs").iterdir()
    }
    for _ in range(2):
        value = verify_actor_release(
            c.spec, c.evidence, c.workspace_root, c.controls.bind(c.op)
        )
        assert value.model == c.spec.artifact
        assert value.engine_config == c.spec.engine_config
        assert value.binding == binding(c)
    assert {p: p.read_bytes() for p in before} == before
    no_resource_effects(c)


def test_node_staged_root_changes_only_location(
    c: ResourceCase, tmp_path: Path
) -> None:
    staged = tmp_path / "staged"
    shutil.copytree(c.spec.artifact.root, staged)
    c.spec = c.spec.model_copy(
        update={"artifact": c.spec.artifact.model_copy(update={"root": str(staged)})}
    )
    verify(c)
    no_resource_effects(c)


@pytest.mark.parametrize(
    "field,value",
    [
        ("component_id", "generator"),
        ("model_artifact_id", "unknown-model"),
        ("engine_config_artifact_id", "unknown-config"),
    ],
)
def test_binding_must_resolve_exact_actor_role(
    c: ResourceCase, field: str, value: str
) -> None:
    replace_binding(c, binding(c).model_copy(update={field: value}))
    with pytest.raises(OwnershipConflict):
        with registered_actor(c.spec, c.op, **c.dependencies()):
            pytest.fail("bad binding started worker")
    no_resource_effects(c)


@pytest.mark.parametrize(
    "field,value", [("dtype", "float32"), ("cpu_threads", 1), ("context_window", 300)]
)
def test_actual_engine_config_cannot_drift(
    c: ResourceCase, field: str, value: object
) -> None:
    c.spec = c.spec.model_copy(
        update={"engine_config": c.spec.engine_config.model_copy(update={field: value})}
    )
    with pytest.raises(OwnershipConflict, match="configuration changed"):
        verify(c)
    no_resource_effects(c)


def test_package_version_is_part_of_configuration(c: ResourceCase) -> None:
    cfg = c.spec.engine_config
    packages = (
        cfg.packages[0].model_copy(update={"version": "0.0.0"}),
        *cfg.packages[1:],
    )
    c.spec = c.spec.model_copy(
        update={"engine_config": cfg.model_copy(update={"packages": packages})}
    )
    with pytest.raises(OwnershipConflict):
        verify(c)


def test_release_reference_is_full_identity(c: ResourceCase) -> None:
    c.spec = c.spec.model_copy(
        update={
            "release_ref": c.spec.release_ref.model_copy(
                update={"producer": "foreign-release"}
            )
        }
    )
    with pytest.raises(OwnershipConflict, match="another release"):
        verify(c)


@pytest.mark.parametrize(
    "field,value", [("interface_id", "legacy-actor"), ("contract_version", "2.0")]
)
def test_unsupported_release_component(c: ResourceCase, field: str, value: str) -> None:
    manifest = ReleaseManifest.model_validate_json(c.evidence.read(c.spec.release_ref))
    replace_manifest(
        c,
        manifest.model_copy(
            update={
                "components": tuple(
                    (
                        x.model_copy(update={field: value})
                        if x.component_id == "actor"
                        else x
                    )
                    for x in manifest.components
                )
            }
        ),
    )
    with pytest.raises(OwnershipConflict):
        verify(c)


@pytest.mark.parametrize("which", ["id", "file_order", "file_hash"])
def test_staged_inventory_is_bound_to_original_model(
    c: ResourceCase, which: str
) -> None:
    artifact = c.spec.artifact
    if which == "id":
        artifact = artifact.model_copy(update={"artifact_id": "different-model"})
    elif which == "file_order":
        artifact = artifact.model_copy(
            update={"files": tuple(reversed(artifact.files))}
        )
    else:
        artifact = artifact.model_copy(
            update={
                "files": (
                    artifact.files[0].model_copy(update={"sha256": "a" * 64}),
                    *artifact.files[1:],
                )
            }
        )
    c.spec = c.spec.model_copy(update={"artifact": artifact})
    with pytest.raises(OwnershipConflict):
        verify(c)


@pytest.mark.parametrize("which", ["binding", "manifest", "config"])
@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_and_damaged_cas(c: ResourceCase, which: str, corrupt: bool) -> None:
    ref = {
        "binding": c.spec.model_binding_ref,
        "manifest": c.spec.release_ref,
        "config": binding(c).engine_config_ref,
    }[which]
    path = c.workspace_root / "evidence/blobs" / ref.sha256
    if corrupt:
        path.write_bytes(b"damaged")
    else:
        path.unlink()
    with pytest.raises(EvidenceIntegrityError if corrupt else EvidenceNotFound):
        verify(c)
    no_resource_effects(c)


@pytest.mark.parametrize("which", ["noncanonical", "duplicate", "invalid", "oversized"])
def test_binding_wire_rejects_ambiguous_or_unbounded_data(
    c: ResourceCase, which: str
) -> None:
    original = c.evidence.read(c.spec.model_binding_ref)
    raw = {
        "noncanonical": json.dumps(json.loads(original), indent=2).encode(),
        "duplicate": b'{"model":"first",' + original[1:],
        "invalid": b"not-json",
        "oversized": b" " * 16385,
    }[which]
    ref = c.evidence.put(raw, metadata("model-binding/1"))
    c.spec = c.spec.model_copy(update={"model_binding_ref": ref})
    with pytest.raises((EvidenceIntegrityError, ValueError)):
        verify(c)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "actor-model-binding/0"),
        ("kind", "checkpoint"),
        ("provider", "openrouter"),
        ("model", ""),
        ("model", None),
        ("component_id", []),
        ("model_artifact_id", True),
    ],
)
def test_binding_contract_invalid_inputs(
    c: ResourceCase, field: str, value: object
) -> None:
    raw = {**binding(c).model_dump(), field: value}
    with pytest.raises(ValidationError):
        ActorModelBinding.model_validate(raw)


@pytest.mark.parametrize(
    "which", ["old_schema", "missing_model_binding", "public_binding"]
)
def test_resource_spec_requires_new_explicit_binding(
    c: ResourceCase, which: str
) -> None:
    value = c.spec.model_dump()
    if which == "old_schema":
        value["schema_version"] = "actor-resource-spec/0"
    elif which == "missing_model_binding":
        value.pop("model_binding_ref")
    else:
        value["model_binding_ref"]["visibility"] = "public"
    with pytest.raises(ValidationError):
        ActorResourceSpec.model_validate(value)


@pytest.mark.parametrize(
    "which", ["writable_root", "writable_file", "missing", "extra", "link", "bytes"]
)
def test_frozen_source_invariants(c: ResourceCase, which: str, tmp_path: Path) -> None:
    root = Path(c.spec.artifact.root)
    target = root / c.spec.artifact.files[0].path
    if which == "writable_root":
        root.chmod(0o755)
    elif which == "writable_file":
        target.chmod(0o644)
    elif which == "bytes":
        target.chmod(0o644)
        target.write_bytes(b"tampered")
        target.chmod(0o444)
    else:
        root.chmod(0o755)
        if which == "missing":
            target.unlink()
        elif which == "extra":
            (root / "extra").write_bytes(b"extra")
        else:
            outside = tmp_path / "link-target"
            outside.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(outside)
        root.chmod(0o555)
    with pytest.raises(EvidenceIntegrityError):
        with registered_actor(c.spec, c.op, **c.dependencies()):
            pytest.fail("invalid frozen files launched")
    no_resource_effects(c)


def test_workspace_is_trusted_input_not_taken_from_manifest(
    c: ResourceCase, tmp_path: Path
) -> None:
    outside = tmp_path / "other-workspace"
    outside.mkdir()
    with pytest.raises(EvidenceIntegrityError, match="outside trusted workspace"):
        verify_actor_release(c.spec, c.evidence, outside, c.controls.bind(c.op))


@pytest.mark.parametrize("value", [None, "workspace", Path("relative")])
def test_invalid_workspace_root(c: ResourceCase, value: object) -> None:
    with pytest.raises(ValueError):
        verify_actor_release(
            c.spec, c.evidence, cast(Path, value), c.controls.bind(c.op)
        )


def test_config_cas_must_match_manifest_file(c: ResourceCase) -> None:
    changed = c.spec.engine_config.model_copy(update={"context_window": 999})
    ref = c.evidence.put(
        changed.model_dump_json().encode(), metadata("actor-engine-config/1")
    )
    replace_binding(c, binding(c).model_copy(update={"engine_config_ref": ref}))
    c.spec = c.spec.model_copy(update={"engine_config": changed})
    with pytest.raises(OwnershipConflict, match="frozen file"):
        verify(c)


def test_cancelled_control_precedes_all_resource_effects(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = c.controls.bind(c.op)

    def stopped() -> float:
        raise OperationStopped("CANCELLED", c.op.operation_id)

    monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(OperationStopped):
        with registered_actor(c.spec, c.op, **c.dependencies()):
            pytest.fail("cancelled launch")
    no_resource_effects(c)
