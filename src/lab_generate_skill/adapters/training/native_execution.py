"""Actual worker return metadata and independent original-source proof checks."""

import hashlib
import json
from pathlib import Path
from typing import Literal
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    NativeTrainingExecution,
    require_training_closure,
)
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import AllocationToken, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.training_output import TrainingWorkerAuthority
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.policies.training_metadata import training_metadata
from .inputs import build_sft_inputs
from .output_files import pin_training_output


def native_metadata() -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema="sft-native-execution/1",
        visibility="private",
        producer="framework-sft-native-v1",
    )


def validate_native_return(
    plan: TrainingOutputPlan, data: LoadedDataset, native: NativeTrainingExecution
) -> None:
    t = plan.training
    expected_plan = evidence_reference(
        t.model_dump_json().encode(), training_metadata("training-plan/1")
    )
    expected_contract = build_sft_inputs(t, data, Path(plan.output_root)).contract
    contract_sha = hashlib.sha256(
        json.dumps(expected_contract, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if (
        native.training_id,
        native.training_plan_ref,
        native.dataset_ref,
        native.training_release_ref,
        native.contract_sha256,
        native.source.root,
    ) != (
        t.training_id,
        expected_plan,
        data.receipt.dataset_ref,
        t.training_release_ref,
        contract_sha,
        plan.output_root,
    ) or (
        native.token.owner.run_id,
        native.token.owner.owner_id,
    ) != (
        t.dataset.operation.run_id,
        t.dataset.operation.owner_id,
    ):
        raise EvidenceIntegrityError(
            "Native return changed exact original plan/dataset/contract/worker output"
        )


class NativeReturnCommitUnconfirmed(RuntimeError):
    def __init__(
        self,
        native: NativeTrainingExecution,
        reference: EvidenceRef,
        primary: BaseException,
    ) -> None:
        self.native, self.reference, self.primary = native, reference, primary
        super().__init__(
            "Original core returned; return evidence acknowledgement unknown, never rerun training"
        )


def publish_native_return(
    plan: TrainingOutputPlan,
    data: LoadedDataset,
    token: AllocationToken,
    worker: ProcessIdentity,
    installation_ref: EvidenceRef,
    evidence: EvidenceStore,
    authority: TrainingWorkerAuthority,
    control: OperationControl,
) -> EvidenceRef:
    plan = TrainingOutputPlan.model_validate(plan)
    token, worker = AllocationToken.model_validate(
        token
    ), ProcessIdentity.model_validate(worker)
    private_state_ref(installation_ref, "release-installation/1")
    authority.verify_capture(plan, data, token, worker, installation_ref, control)
    source = pin_training_output(plan, control)
    assert data.receipt.dataset_ref is not None
    contract = build_sft_inputs(plan.training, data, Path(plan.output_root)).contract
    native = NativeTrainingExecution(
        training_id=plan.training.training_id,
        training_plan_ref=evidence_reference(
            plan.training.model_dump_json().encode(),
            training_metadata("training-plan/1"),
        ),
        dataset_ref=data.receipt.dataset_ref,
        training_release_ref=plan.training.training_release_ref,
        installation_ref=installation_ref,
        token=token,
        worker=worker,
        contract_sha256=hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        returned=True,
        source=source,
    )
    authority.verify_return(plan, data, native, control)
    raw = native.model_dump_json().encode()
    ref = evidence_reference(raw, native_metadata())
    try:
        control.checkpoint()
        if (
            EvidenceRef.model_validate(evidence.put(raw, native_metadata(), control))
            != ref
            or evidence.read(ref, control) != raw
        ):
            raise EvidenceIntegrityError(
                "Original worker return publication/readback changed"
            )
        control.checkpoint()
        return ref
    except BaseException as error:
        raise NativeReturnCommitUnconfirmed(native, ref, error) from error


class OriginalTrainingOutputAuthority:
    def __init__(
        self, evidence: EvidenceReader, worker: TrainingWorkerAuthority
    ) -> None:
        if not callable(getattr(worker, "verify_closed", None)):
            raise ValueError(
                "Actual original worker/runtime closure authority required"
            )
        self.evidence, self.worker = evidence, worker

    def verify(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        closure: ClosureReceipt,
        execution_ref: EvidenceRef,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> NativeTrainingExecution:
        require_training_closure(plan, closure)
        if (
            execution_ref.visibility,
            execution_ref.content_schema,
            execution_ref.media_type,
            execution_ref.producer,
        ) != (
            "private",
            "sft-native-execution/1",
            "application/json",
            "framework-sft-native-v1",
        ) or not 0 < execution_ref.size_bytes <= 8 * 1024**2:
            raise EvidenceIntegrityError(
                "Original bounded actual native return reference required"
            )
        control.checkpoint()
        raw = self.evidence.read(execution_ref, control)
        if (
            type(raw) is not bytes
            or evidence_reference(raw, native_metadata()) != execution_ref
        ):
            raise EvidenceIntegrityError("Native return source bytes changed")
        parsed = json_object(raw)
        if parsed.get("returned") is not True:
            raise EvidenceIntegrityError(
                "Only known original native return permits output publication"
            )
        native = NativeTrainingExecution.model_validate_json(raw)
        if native.model_dump_json().encode() != raw or native.token != closure.token:
            raise EvidenceIntegrityError(
                "Native execution and closure changed original worker/resource"
            )
        validate_native_return(plan, data, native)
        original_plan = self.evidence.read(native.training_plan_ref, control)
        if (
            type(original_plan) is not bytes
            or evidence_reference(original_plan, training_metadata("training-plan/1"))
            != native.training_plan_ref
            or TrainingPlan.model_validate_json(original_plan) != plan.training
        ):
            raise EvidenceIntegrityError(
                "Original training plan publication is missing or changed"
            )
        self.worker.verify_closed(plan, data, native, closure, phase, control)
        control.checkpoint()
        return native
