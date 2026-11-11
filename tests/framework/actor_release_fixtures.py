"""Real model/config manifest slice; all unrelated release roles are synthetic."""

import hashlib
from pathlib import Path
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.release import (
    ReleaseArtifact,
    ReleaseFile,
    ReleaseManifest,
)
from release_fixtures import frozen


def metadata(schema: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="engineering-actor-release",
    )


def freeze_model_release(
    root: Path,
    evidence: FileEvidenceStore,
    model: ReleaseArtifact,
    config: ActorEngineConfig,
    *,
    model_name: str = "unit/qwen2",
    installation: ReleaseManifest | None = None,
) -> tuple[EvidenceRef, EvidenceRef]:
    root.mkdir()
    base = installation if installation is not None else frozen(root / "other-roles")
    raw = config.model_dump_json().encode()
    config_ref = evidence.put(raw, metadata(config.schema_version))
    config_root = root / "engine-config"
    config_root.mkdir()
    path = config_root / "actor-engine-config.json"
    path.write_bytes(raw)
    path.chmod(0o444)
    config_root.chmod(0o555)
    artifact = ReleaseArtifact(
        artifact_id="actor-engine-config",
        root=str(config_root),
        files=(
            ReleaseFile(
                path=path.name,
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                executable=False,
            ),
        ),
    )
    manifest = ReleaseManifest.model_validate(
        base.model_copy(
            update={
                "artifacts": (*base.artifacts, model, artifact),
                "components": tuple(
                    (
                        c.model_copy(
                            update={
                                "interface_id": "local-actor-engine",
                                "contract_version": "1.0",
                                "artifact_ids": (
                                    model.artifact_id,
                                    artifact.artifact_id,
                                ),
                            }
                        )
                        if c.component_id == "actor"
                        else c
                    )
                    for c in base.components
                ),
            }
        )
    )
    release_ref = evidence.put(
        manifest.model_dump_json().encode(), metadata("release-manifest/1")
    )
    binding = ActorModelBinding(
        model=model_name,
        release_ref=release_ref,
        component_id="actor",
        model_artifact_id=model.artifact_id,
        engine_config_artifact_id=artifact.artifact_id,
        engine_config_ref=config_ref,
    )
    return release_ref, evidence.put(
        binding.model_dump_json().encode(), metadata("model-binding/1")
    )
