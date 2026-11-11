"""Original TrainingExecution port composed with the registered fixed worker."""

import hashlib
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingLaunch,
)
from lab_generate_skill.domain.training_worker_call import TrainingWorkerCommand
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    ResourceJournal,
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.training import TrainingAuthority
from lab_generate_skill.ports.training_resource import TrainingResourceAuthority
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from .resource import RegisteredTrainingResource
from .resource_records import metadata
from .inputs import build_sft_inputs


class RegisteredTrainingExecution:
    def __init__(
        self,
        spec: TrainingResourceSpec,
        *,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        source_authority: TrainingAuthority,
        resource_authority: TrainingResourceAuthority,
        allocation_verifier: SlurmAllocationVerifier,
    ) -> None:
        self.spec = TrainingResourceSpec.model_validate(spec)
        self.journal, self.evidence, self.controls, self.clock = (
            journal,
            evidence,
            controls,
            clock,
        )
        self.source_authority, self.resource_authority, self.allocation_verifier = (
            source_authority,
            resource_authority,
            allocation_verifier,
        )
        self.resource: RegisteredTrainingResource | None = None
        self.state = "new"

    def _bound(
        self, plan: TrainingPlan, data: LoadedDataset, output: Path
    ) -> dict[str, Any]:
        c = self.spec.configuration.output
        if plan != c.training or str(output) != c.output_root:
            raise EvidenceIntegrityError(
                "Training execution changed original plan/output"
            )
        return build_sft_inputs(plan, data, output).contract

    def verify(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> None:
        if self.state != "new":
            raise OwnershipConflict(
                "Original training admission/acquisition cannot be repeated"
            )
        self.state = "admitting"
        contract = self._bound(plan, data, output)
        control.checkpoint()
        self.source_authority.verify(plan, data, control)
        digest = hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        command = TrainingWorkerCommand(
            session_id=self.spec.configuration.token.expected_resource_id,
            sequence=2,
            operation="train",
            remaining_seconds=control.checkpoint(),
            contract_sha256=digest,
        )
        ref = evidence_reference(
            command.model_dump_json().encode(), metadata("sft-worker-command/1")
        )
        launch = TrainingLaunch(spec=self.spec, train=command, command_ref=ref)
        self.resource = RegisteredTrainingResource(
            launch,
            journal=self.journal,
            evidence=self.evidence,
            controls=self.controls,
            clock=self.clock,
            authority=self.resource_authority,
            allocation_verifier=self.allocation_verifier,
        )
        self.resource.start(control)
        self.state = "admitted"

    def execute(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        contract: dict[str, Any],
        control: OperationControl,
    ) -> EvidenceRef:
        if (
            self._bound(plan, data, output) != contract
            or self.state != "admitted"
            or self.resource is None
        ):
            raise OwnershipConflict(
                "Only original exact admitted training may execute once"
            )
        self.state = "executing"
        self.source_authority.verify(plan, data, control)
        result = self.resource.invoke(data, control)
        self.state = "returned"
        return result

    def close(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        control: OperationControl,
    ) -> ClosureReceipt:
        self._bound(plan, data, output)
        if self.resource is None:
            raise OwnershipConflict("No original training resource to close")
        result = self.resource.close(control)
        self.state = "closed"
        return result

    def abort(
        self,
        plan: TrainingPlan,
        data: LoadedDataset,
        output: Path,
        primary: BaseException,
        control: OperationControl,
    ) -> None:
        self._bound(plan, data, output)
        if self.resource is not None and self.resource.owned:
            if self.resource.primary is None:
                self.resource.primary = primary
            self.resource.close(control)
        self.state = "aborted"
