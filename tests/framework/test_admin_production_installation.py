"""Pure site-role declarations, never evidence of an actual installed Admin."""

import json
from pathlib import Path
import pytest
from admin_production_installation import admin_role_declaration
from production_installation import MapExecutionInstallation, reference
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.release import ReleaseManifest, ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "experiments/framework-admin-navigation-production-20261102-v1"


def original() -> MapExecutionInstallation:
    d = json.loads(
        (
            W
            / "experiments/framework-map-navigation42-production-20261102-v1/deployment-4900890/deployment.json"
        ).read_text()
    )
    return MapExecutionInstallation(
        ReleaseInstallation.model_validate_json(json.dumps(d["installation"])),
        ActorModelBinding.model_validate_json(json.dumps(d["actor"])),
        ActorEngineConfig.model_validate_json(json.dumps(d["config"])),
        d["preparation"],
    )


def test_old_installed_map_payload_cannot_be_relabelled_as_current_admin() -> None:
    software = (P / "check-isolated-4902406/result.json").read_bytes()
    with pytest.raises(ValueError, match="old or different"):
        admin_role_declaration(original(), software)


def test_complete_declared_admin_code_keeps_actor_and_inactive_roles() -> None:
    base = original()
    software = (P / "check-isolated-4902406/result.json").read_bytes()
    current = json.loads(software)
    code = next(
        a
        for a in base.declaration.manifest.artifacts
        if a.artifact_id == "installed-code"
    )
    # Explicit unit inventory: there is no installation at this path. The
    # real producer below this pure helper must build and verify actual files.
    declared = code.model_copy(
        update={
            "root": "/unit-not-installed/admin-code",
            "files": tuple(
                ReleaseFile(
                    path=name.removeprefix("src/"),
                    sha256=sha,
                    size_bytes=1,
                    executable=False,
                )
                for name, sha in current["files"].items()
                if name.startswith("src/lab_generate_skill/") and name.endswith(".py")
            ),
        }
    )
    manifest = ReleaseManifest.model_validate(
        base.declaration.manifest.model_copy(
            update={
                "artifacts": tuple(
                    declared if a.artifact_id == code.artifact_id else a
                    for a in base.declaration.manifest.artifacts
                ),
            }
        )
    )
    manifest_ref = reference(
        manifest.model_dump_json().encode(), manifest.schema_version
    )
    fake_base = MapExecutionInstallation(
        ReleaseInstallation(
            manifest_ref=manifest_ref,
            manifest=manifest,
            workspace_root=base.declaration.workspace_root,
            python_executable=base.declaration.python_executable,
        ),
        base.actor.model_copy(update={"release_ref": manifest_ref}),
        base.engine_config,
        {"unit_declaration_only": True},
    )
    value = admin_role_declaration(fake_base, software)
    assert value.engine_config == base.engine_config
    assert value.actor.engine_config_ref == base.actor.engine_config_ref
    assert value.actor.model_artifact_id == base.actor.model_artifact_id
    assert value.actor.release_ref == value.declaration.manifest_ref
    assert {r.scope_id for r in value.declaration.manifest.roles} == {
        "global",
        "shopping_admin",
    }
    assert all(
        c.interface_id == "inactive-engineering-role"
        for c in value.declaration.manifest.components
        if c.component_id in {"generator", "teacher", "encoder", "teacher_processor"}
    )
    assert value.preparation["source_or_resource_permission"] is False
