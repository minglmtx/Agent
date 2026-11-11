"""Full original checkpoint files -> small canonical reference -> readonly replay."""

from pathlib import Path
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    SFTCheckpoint,
    NativeTrainingExecution,
    output_artifact_id,
    require_training_closure,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.training_output import TrainingOutputAuthority
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.adapters.releases.files import verify_artifact
from lab_generate_skill.adapters.processes.wire_json import json_object
from .output_files import pin_training_output
from .native_output import native_training_outcome


def checkpoint_metadata() -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema="sft-checkpoint/1",
        visibility="private",
        producer="framework-sft-output-v1",
    )


class CheckpointPublicationUnconfirmed(RuntimeError):
    def __init__(
        self,
        plan: TrainingOutputPlan,
        phase: str,
        primary: BaseException,
        artifact: object,
        reference: EvidenceRef | None,
    ) -> None:
        self.plan, self.phase, self.primary, self.artifact, self.reference = (
            plan,
            phase,
            primary,
            artifact,
            reference,
        )
        super().__init__(
            "Native SFT snapshot unconfirmed; preserve all files and candidate ref, no training retry"
        )


class SFTOutputStore:
    def __init__(
        self,
        workspace: Path,
        evidence: EvidenceStore,
        authority: TrainingOutputAuthority,
    ) -> None:
        if (
            not isinstance(workspace, Path)
            or not workspace.is_absolute()
            or ".." in workspace.parts
            or not callable(getattr(authority, "verify", None))
        ):
            raise ValueError(
                "Trusted canonical workspace and actual original output authority required"
            )
        self.workspace, self.evidence, self.authority = workspace, evidence, authority

    def publish(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        closure: ClosureReceipt,
        execution_ref: EvidenceRef,
        control: OperationControl,
    ) -> EvidenceRef:
        plan = TrainingOutputPlan.model_validate(plan)
        require_training_closure(plan, closure)
        private_state_ref(execution_ref, "sft-native-execution/1")
        if str(self.workspace) != plan.workspace_root:
            raise ValueError("Publication plan changed trusted workspace")
        phase = "original_output_admission"
        artifact = None
        reference = None
        try:
            control.checkpoint()
            returned = NativeTrainingExecution.model_validate(
                self.authority.verify(
                    plan, data, closure, execution_ref, "capture", control
                )
            )
            phase = "complete_native_output_pin"
            source = pin_training_output(plan, control)
            if source != returned.source:
                raise EvidenceIntegrityError(
                    "Output changed after original native worker return"
                )
            phase = "complete_file_freeze"
            artifact = FileArtifactFreezer(
                self.workspace, Path(plan.publication_root)
            ).freeze(source, output_artifact_id(source), control)
            phase = "native_contract_and_checkpoint"
            native = native_training_outcome(plan, data, artifact, control)
            assert data.receipt.dataset_ref is not None
            snapshot = SFTCheckpoint(
                plan=plan,
                dataset_ref=data.receipt.dataset_ref,
                source=source,
                artifact=artifact,
                native=native,
                closure=closure,
                execution_ref=execution_ref,
            )
            if (
                self.authority.verify(
                    plan, data, closure, execution_ref, "publish", control
                )
                != returned
            ):
                raise EvidenceIntegrityError(
                    "Original native worker return changed during publication"
                )
            raw = snapshot.model_dump_json().encode()
            reference = evidence_reference(raw, checkpoint_metadata())
            phase = "small_checkpoint_reference"
            control.checkpoint()
            actual = EvidenceRef.model_validate(
                self.evidence.put(raw, checkpoint_metadata(), control)
            )
            if actual != reference:
                raise EvidenceIntegrityError(
                    "Native checkpoint publication returned foreign reference"
                )
            # Readback uses the same complete-file and original-proof path as an
            # independent consumer; no metadata-only successful publication.
            if self.read(reference, data, control) != snapshot:
                raise EvidenceIntegrityError(
                    "Native checkpoint readback changed original output"
                )
            return reference
        except BaseException as error:
            if artifact is None:
                artifact = getattr(error, "artifact_freeze", None)
            raise CheckpointPublicationUnconfirmed(
                plan, phase, error, artifact, reference
            ) from error

    def read(
        self, reference: EvidenceRef, data: LoadedDataset, control: OperationControl
    ) -> SFTCheckpoint:
        reference = EvidenceRef.model_validate(reference)
        if (
            reference.visibility,
            reference.content_schema,
            reference.media_type,
            reference.producer,
        ) != (
            "private",
            "sft-checkpoint/1",
            "application/json",
            "framework-sft-output-v1",
        ) or not 0 < reference.size_bytes <= 8 * 1024**2:
            raise EvidenceIntegrityError(
                "Exact bounded original SFT checkpoint metadata required"
            )
        control.checkpoint()
        raw = self.evidence.read(reference, control)
        if (
            type(raw) is not bytes
            or evidence_reference(raw, checkpoint_metadata()) != reference
        ):
            raise EvidenceIntegrityError(
                "Native checkpoint metadata differs from complete original bytes"
            )
        json_object(raw)
        snapshot = SFTCheckpoint.model_validate_json(raw)
        if (
            snapshot.model_dump_json().encode() != raw
            or snapshot.plan.workspace_root != str(self.workspace)
            or snapshot.dataset_ref != data.receipt.dataset_ref
        ):
            raise EvidenceIntegrityError(
                "Checkpoint changed canonical source/dataset/workspace"
            )
        returned = NativeTrainingExecution.model_validate(
            self.authority.verify(
                snapshot.plan,
                data,
                snapshot.closure,
                snapshot.execution_ref,
                "read",
                control,
            )
        )
        if returned.source != snapshot.source:
            raise EvidenceIntegrityError(
                "Checkpoint changed original native worker file inventory"
            )
        verify_artifact(snapshot.artifact, control)
        actual = native_training_outcome(
            snapshot.plan, data, snapshot.artifact, control
        )
        if actual != snapshot.native:
            raise EvidenceIntegrityError(
                "Stored checkpoint outcome differs from original native files"
            )
        self.authority.verify(
            snapshot.plan,
            data,
            snapshot.closure,
            snapshot.execution_ref,
            "read",
            control,
        )
        control.checkpoint()
        return snapshot
