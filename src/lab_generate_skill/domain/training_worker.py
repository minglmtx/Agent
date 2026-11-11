"""Original installed SFT child binding; configuration alone grants no training rights."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .training_output import TrainingOutputPlan
from .lifecycle import AllocationToken
from .release_installation import ReleaseInstallation
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class TrainingWorkerConfiguration(Contract):
    schema_version: Literal["sft-worker-configuration/1"] = "sft-worker-configuration/1"
    output: TrainingOutputPlan
    token: AllocationToken
    installation: ReleaseInstallation
    installation_ref: EvidenceRef
    evidence_root: str

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        t, a, i = self.output.training, self.token, self.installation
        root, workspace = PurePosixPath(self.evidence_root), PurePosixPath(
            self.output.workspace_root
        )
        private_state_ref(self.installation_ref, "release-installation/1")
        raw = i.model_dump_json().encode()
        if (self.installation_ref.sha256, self.installation_ref.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise ValueError("Exact complete original installation reference required")
        if (
            t.training_release_ref != i.manifest_ref
            or i.workspace_root != self.output.workspace_root
        ):
            raise ValueError(
                "Training, installation and workspace must use the same release"
            )
        if (a.scope, a.resource_kind, a.provider_id, a.provider_version) != (
            "batch",
            "trainer_model",
            "fixed-sft-worker",
            "1",
        ) or (a.owner.run_id, a.owner.owner_id) != (
            t.dataset.operation.run_id,
            t.dataset.operation.owner_id,
        ):
            raise ValueError(
                "Original batch trainer allocation/provider/owner required"
            )
        if (
            not root.is_absolute()
            or str(root) != self.evidence_root
            or ".." in root.parts
            or any(c in self.evidence_root for c in ("\0", "\\"))
            or len(self.evidence_root) > 4096
            or root == workspace
            or not root.is_relative_to(workspace)
        ):
            raise ValueError(
                "Explicit canonical existing private evidence subtree required"
            )
        for value in (self.output.output_root, self.output.publication_root):
            other = PurePosixPath(value)
            if root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError(
                    "Evidence and training output/publication must be disjoint"
                )
        if len(self.model_dump_json().encode()) > 15 * 1024**2:
            raise ValueError("Training worker configuration exceeds wire bound")
        return self
