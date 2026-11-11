"""Parent-side fixed original SFT release/model slice; no phase or launch grant."""

from pathlib import Path
from lab_generate_skill.domain.training_resource import TrainingResourceSpec
from lab_generate_skill.domain.causal_model import validate_causal_artifact
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.documents import EvidenceReleaseDocuments
from lab_generate_skill.adapters.releases.files import verify_artifact
from lab_generate_skill.policies.training_metadata import training_metadata
from .worker_data import original_document


def verify_training_release(
    spec: TrainingResourceSpec, evidence: EvidenceStore, control: OperationControl
) -> None:
    c = spec.configuration
    workspace = Path(c.output.workspace_root)
    control.checkpoint()
    if workspace.resolve(strict=True) != workspace or not workspace.is_dir():
        raise EvidenceIntegrityError(
            "Original training workspace is unavailable/aliased"
        )
    if (
        original_document(c.installation_ref, ReleaseInstallation, evidence, control)
        != c.installation
    ):
        raise EvidenceIntegrityError("Stored original training installation changed")
    manifest = EvidenceReleaseDocuments(evidence).manifest(
        c.installation.manifest_ref, control
    )
    if manifest != c.installation.manifest:
        raise EvidenceIntegrityError(
            "Original training release changed complete installed manifest"
        )
    ref = evidence_reference(
        c.output.training.model_dump_json().encode(),
        training_metadata("training-plan/1"),
    )
    if original_document(ref, TrainingPlan, evidence, control) != c.output.training:
        raise EvidenceIntegrityError("Original published training plan changed")
    role = next(
        r for r in manifest.roles if (r.role, r.scope_id) == ("generator", "global")
    )
    component = next(
        v for v in manifest.components if v.component_id == role.component_id
    )
    if (
        component.interface_id != "local-generator-engine"
        or component.contract_version != "1.0"
    ):
        raise OwnershipConflict(
            "Original generator base model release interface required for SFT"
        )
    requested = validate_causal_artifact(c.output.training.model)
    original = next(
        (a for a in manifest.artifacts if a.artifact_id == requested.artifact_id), None
    )
    if (
        original is None
        or requested.artifact_id not in component.artifact_ids
        or requested.files != original.files
    ):
        raise OwnershipConflict(
            "Training base model differs from original generator release artifact"
        )
    for artifact in (
        (original,) if original.root == requested.root else (original, requested)
    ):
        root = Path(artifact.root)
        if root == workspace or not root.is_relative_to(workspace):
            raise OwnershipConflict(
                "Original/staged training model left its trusted workspace"
            )
        verify_artifact(artifact, control)
