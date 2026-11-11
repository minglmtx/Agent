"""Actual release/model/config validation before resource registration or spawn.

No default authority, file repair, imports, downloads or current-release lookup.
Only the Generator model/config slice is verified here; installation, other
release roles, Slurm/exclusive ownership and inference remain separate checks.
All synchronous evidence/filesystem I/O requires outer process supervision.
"""

from lab_generate_skill.domain.causal_model import validate_causal_artifact

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generator_engine import (
    GeneratorEngineConfig,
)
from lab_generate_skill.domain.generator_model_binding import GeneratorModelBinding
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseManifest
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.adapters.releases.documents import EvidenceReleaseDocuments
from lab_generate_skill.adapters.releases.files import verify_artifact

T = TypeVar("T", bound=Contract)


@dataclass(frozen=True)
class ResolvedGeneratorRelease:
    binding: GeneratorModelBinding
    manifest: ReleaseManifest
    model: ReleaseArtifact
    engine_config: GeneratorEngineConfig


def _document(
    store: EvidenceStore,
    reference: EvidenceRef,
    schema: str,
    model: type[T],
    control: OperationControl,
) -> T:
    private_state_ref(reference, schema)
    if not 0 < reference.size_bytes <= 16384:
        raise EvidenceIntegrityError("Generator release document exceeds byte budget")
    control.checkpoint()
    raw = store.read(reference, control=control)
    if (
        type(raw) is not bytes
        or len(raw) != reference.size_bytes
        or hashlib.sha256(raw).hexdigest() != reference.sha256
    ):
        raise EvidenceIntegrityError(
            "Generator release document differs from reference"
        )
    json_object(raw)
    value = model.model_validate_json(raw)
    if value.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Generator release document is not canonical")
    control.checkpoint()
    return value


def verify_generator_release(
    spec: GeneratorResourceSpec,
    evidence: EvidenceStore,
    workspace_root: Path,
    control: OperationControl,
) -> ResolvedGeneratorRelease:
    """Return exact resolved facts, never a reusable execution/launch permit."""
    spec = GeneratorResourceSpec.model_validate(spec)
    if not isinstance(workspace_root, Path) or not workspace_root.is_absolute():
        raise ValueError("Trusted workspace root must be an absolute Path")
    control.checkpoint()
    if (
        workspace_root.resolve(strict=True) != workspace_root
        or not workspace_root.is_dir()
    ):
        raise EvidenceIntegrityError("Trusted workspace root is not canonical")
    binding = _document(
        evidence,
        spec.model_binding_ref,
        "model-binding/1",
        GeneratorModelBinding,
        control,
    )
    if binding.release_ref != spec.release_ref:
        raise OwnershipConflict("Generator binding belongs to another release")
    manifest = EvidenceReleaseDocuments(evidence).manifest(spec.release_ref, control)
    role = next(
        r for r in manifest.roles if (r.role, r.scope_id) == ("generator", "global")
    )
    component = next(
        c for c in manifest.components if c.component_id == role.component_id
    )
    if (
        binding.component_id != component.component_id
        or component.interface_id != "local-generator-engine"
        or component.contract_version != "1.0"
        or set(component.artifact_ids)
        != {binding.model_artifact_id, binding.engine_config_artifact_id}
    ):
        raise OwnershipConflict(
            "Generator binding differs from the frozen release role"
        )
    artifacts = {a.artifact_id: a for a in manifest.artifacts}
    model = validate_causal_artifact(artifacts[binding.model_artifact_id])
    configuration = artifacts[binding.engine_config_artifact_id]
    if len(configuration.files) != 1:
        raise OwnershipConflict(
            "Generator engine config artifact needs exactly one file"
        )
    entry = configuration.files[0]
    if (entry.path, entry.sha256, entry.size_bytes, entry.executable) != (
        "generator-engine-config.json",
        binding.engine_config_ref.sha256,
        binding.engine_config_ref.size_bytes,
        False,
    ):
        raise OwnershipConflict("Generator config reference differs from frozen file")
    config = _document(
        evidence,
        binding.engine_config_ref,
        "generator-engine-config/1",
        GeneratorEngineConfig,
        control,
    )
    if config != spec.engine_config:
        raise OwnershipConflict("Actual Generator engine configuration changed")
    if (spec.artifact.artifact_id, spec.artifact.files) != (
        model.artifact_id,
        model.files,
    ):
        raise OwnershipConflict(
            "Staged Generator model differs from frozen release inventory"
        )
    for artifact in (model, configuration):
        root = Path(artifact.root)
        if root == workspace_root or not root.is_relative_to(workspace_root):
            raise EvidenceIntegrityError(
                "Generator source artifact is outside trusted workspace"
            )
        verify_artifact(artifact, control)
    if spec.artifact.root != model.root:
        verify_artifact(spec.artifact, control)
    control.checkpoint()
    return ResolvedGeneratorRelease(binding, manifest, model, config)
