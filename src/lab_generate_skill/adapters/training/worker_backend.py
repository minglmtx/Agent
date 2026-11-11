"""Fixed installed child leaf for the sole original SFT algorithm.

Used only after original parent dataset/phase admission and durable acquisition.
The kernel guard and installed release are checked before this object exists.
Configuration creates no root, loads no dataset/model, and starts no training.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    NativeTrainingExecution,
)
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import AllocationToken, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.processes.owner_supervisor import observed_guard
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.releases.files import verify_artifact
from lab_generate_skill.policies.training_metadata import training_metadata
from .inputs import build_sft_inputs
from .worker_data import original_document, read_training_data
from .native_execution import publish_native_return, validate_native_return


class WorkerEvidence:
    """Synchronous primitive only inside this externally supervised fixed child."""

    def __init__(self, configuration: TrainingWorkerConfiguration) -> None:
        root = Path(configuration.evidence_root)
        if (
            root.resolve(strict=True) != root
            or not root.is_dir()
            or root.stat().st_uid != os.getuid()
            or root.stat().st_mode & 0o077
        ):
            raise EvidenceIntegrityError(
                "Existing canonical owned private CAS required"
            )
        self.store = FileEvidenceStore(
            root, max_object_bytes=8 * 1024**2, initialize=False
        )

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        result = self.store.read(reference)
        control.checkpoint()
        return result

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        result = self.store.put(data, metadata)
        control.checkpoint()
        return result


class FixedTrainingBackend:
    def __init__(
        self,
        configuration: TrainingWorkerConfiguration,
        guard: ProcessOwnerGuard,
        owner_fd: int,
    ) -> None:
        self.configuration, self.guard, self.owner_fd = configuration, guard, owner_fd
        self.state = "configured"

    def _guard(self, control: OperationControl) -> None:
        if (
            observed_guard(
                self.guard.controller, self.guard.supervisor, self.owner_fd, control
            )
            != self.guard
        ):
            raise OwnershipConflict("Original training parent/worker guard changed")

    def execute(self, contract_sha256: str, control: OperationControl) -> EvidenceRef:
        if self.state != "configured":
            raise OwnershipConflict(
                "Training invocation is single-use; no automatic retry"
            )
        self.state = "executing"
        self._guard(control)
        c = self.configuration
        evidence = WorkerEvidence(c)
        if (
            original_document(
                c.installation_ref, type(c.installation), evidence, control
            )
            != c.installation
        ):
            raise EvidenceIntegrityError("Original stored installation changed")
        ref = evidence_reference(
            c.output.training.model_dump_json().encode(),
            training_metadata("training-plan/1"),
        )
        if original_document(ref, TrainingPlan, evidence, control) != c.output.training:
            raise EvidenceIntegrityError("Original stored training plan changed")
        data = read_training_data(c.output.training, evidence, control)
        request = build_sft_inputs(c.output.training, data, Path(c.output.output_root))
        actual = hashlib.sha256(
            json.dumps(request.contract, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        if actual != contract_sha256:
            raise EvidenceIntegrityError(
                "Training command changed original complete dataset/contract"
            )
        self._guard(control)
        verify_artifact(c.output.training.model, control)
        # Sole fixed algorithm, imported only after original byte/guard checks.
        from .torch_sft import run_original_sft

        run_original_sft(
            request.args, request.train, request.dev, request.contract, control
        )
        self.state = "returned"
        # Known return evidence has its own finite cleanup budget, never a retry.
        cleanup = DeadlineControl(
            c.output.training.cleanup_seconds, "sft-native-return"
        )
        return publish_native_return(
            c.output,
            data,
            c.token,
            self.guard.worker,
            c.installation_ref,
            evidence,
            self,
            cleanup,
        )

    def verify_capture(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        token: AllocationToken,
        worker: ProcessIdentity,
        installation_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        self._guard(control)
        c = self.configuration
        if self.state != "returned" or (plan, token, worker, installation_ref) != (
            c.output,
            c.token,
            self.guard.worker,
            c.installation_ref,
        ):
            raise OwnershipConflict(
                "Only this original known-returned installed child may pin output"
            )
        build_sft_inputs(plan.training, data, Path(plan.output_root))

    def verify_return(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        control: OperationControl,
    ) -> None:
        self.verify_capture(
            plan, data, native.token, native.worker, native.installation_ref, control
        )
        validate_native_return(plan, data, native)

    def verify_closed(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> None:
        raise OwnershipConflict(
            "Live child cannot self-certify full resource closure or later reader rights"
        )

    def close(self, control: OperationControl) -> None:
        control.checkpoint()
        self.state = "closed"
        # Process exit releases the sole original model; full GPU/step-tree proof
        # belongs to the original registered parent, not this child or its reply.
