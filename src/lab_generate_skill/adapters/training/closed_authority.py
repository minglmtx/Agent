"""Closed original resource/wire/source proof reads; no live query or new grant."""

from typing import Literal
from lab_generate_skill.domain.training_resource import (
    TrainingResourceSpec,
    TrainingLaunch,
    TrainingResourceAcquired,
    TrainingResourceClosed,
)
from lab_generate_skill.domain.training_output import (
    TrainingOutputPlan,
    NativeTrainingExecution,
    require_training_closure,
)
from lab_generate_skill.domain.training_worker_call import TrainingWorkerCommand
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ClosureReceipt,
    ResourceRecord,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.training_resource import TrainingResourceAuthority
from lab_generate_skill.adapters.processes.wire_json import json_object
from .worker_data import original_document
from .worker_protocol import decode_reply, TrainingWorkerReply
from .native_execution import validate_native_return, native_metadata
import hashlib


class ClosedTrainingWorkerAuthority:
    def __init__(
        self,
        spec: TrainingResourceSpec,
        evidence: EvidenceReader,
        authority: TrainingResourceAuthority,
    ) -> None:
        self.spec, self.evidence, self.authority = (
            TrainingResourceSpec.model_validate(spec),
            evidence,
            authority,
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
        raise OwnershipConflict(
            "Closed reader cannot impersonate original known-return child"
        )

    def verify_return(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        control: OperationControl,
    ) -> None:
        raise OwnershipConflict(
            "Closed reader cannot publish a new original model return"
        )

    def verify_closed(
        self,
        plan: TrainingOutputPlan,
        data: LoadedDataset,
        native: NativeTrainingExecution,
        closure: ClosureReceipt,
        phase: Literal["capture", "publish", "read"],
        control: OperationControl,
    ) -> None:
        c = self.spec.configuration
        require_training_closure(plan, closure)
        if (
            plan != c.output
            or native.token != c.token
            or closure.token != c.token
            or native.installation_ref != c.installation_ref
        ):
            raise OwnershipConflict("Closed training proof changed original scope")
        self.authority.authorize_read(self.spec, native, closure, phase, control)
        validate_native_return(plan, data, native)
        refs = {r.content_schema: r for r in closure.evidence}
        if len(closure.evidence) != 2 or set(refs) != {
            "sft-resource-closed/1",
            "resource-record/2",
        }:
            raise EvidenceIntegrityError(
                "Original closed resource record/ending refs required"
            )
        ending = original_document(
            refs["sft-resource-closed/1"],
            TrainingResourceClosed,
            self.evidence,
            control,
        )
        record = original_document(
            refs["resource-record/2"], ResourceRecord, self.evidence, control
        )
        if (
            record.token != c.token
            or [e.state for e in record.events]
            != ["registered", "acquiring", "acquired", "closing", "closed"]
            or record.events[-1].evidence != (refs["sft-resource-closed/1"],)
            or ending.status != "closed"
            or ending.primary_error is not None
            or ending.cleanup_errors
            or ending.step is None
            or not ending.start_attempted
            or ending.termination.state != "reaped"
            or ending.termination.cleanup_errors
            or ending.acquired_ref is None
            or ending.reply_ref is None
            or closure.operation_id != ending.operation.parent_operation_id
        ):
            raise EvidenceIntegrityError(
                "Original complete trainer closure/journal outcome mismatch"
            )
        intent = original_document(
            record.events[1].evidence[0],
            ResourceAcquisitionIntent,
            self.evidence,
            control,
        )
        launch = original_document(
            intent.configuration_ref, TrainingLaunch, self.evidence, control
        )
        if (
            launch.spec != self.spec
            or intent.operation != self.spec.operation
            or intent.token != c.token
            or ending.launch_ref != intent.configuration_ref
            or record.events[2].evidence != (ending.acquired_ref,)
        ):
            raise EvidenceIntegrityError(
                "Original persistent training launch/intent changed"
            )
        acquired = original_document(
            ending.acquired_ref, TrainingResourceAcquired, self.evidence, control
        )
        configured = original_document(
            acquired.configure_command_ref,
            TrainingWorkerCommand,
            self.evidence,
            control,
        )
        config_raw = self.evidence.read(acquired.configure_reply_ref, control)
        if (len(config_raw), hashlib.sha256(config_raw).hexdigest()) != (
            acquired.configure_reply_ref.size_bytes,
            acquired.configure_reply_ref.sha256,
        ):
            raise EvidenceIntegrityError("Original configure reply bytes changed")
        configured_reply = decode_reply(configured, config_raw)
        if (
            configured.configuration != c
            or configured_reply.guard != acquired.guard
            or configured_reply.installed != acquired.installed
            or acquired.launch_ref != intent.configuration_ref
            or native.worker != acquired.guard.worker
            or ending.step.target != acquired.step.controller.target
            or ending.launcher is None
            or ending.launcher != ending.step.target.launcher
            or ending.termination.process_id != ending.launcher.process_id
        ):
            raise EvidenceIntegrityError(
                "Actual original installed worker/step/closure binding changed"
            )
        saved_command = original_document(
            launch.command_ref, TrainingWorkerCommand, self.evidence, control
        )
        reply = original_document(
            ending.reply_ref, TrainingWorkerReply, self.evidence, control
        )
        reply = decode_reply(saved_command, reply.model_dump_json().encode())
        expected_native = evidence_reference(
            native.model_dump_json().encode(), native_metadata()
        )
        if (
            saved_command != launch.train
            or reply.status != "ok"
            or reply.execution_ref != expected_native
            or ending.execution_ref != expected_native
        ):
            raise EvidenceIntegrityError(
                "Original training wire/native return changed or remains unknown"
            )
        # Full original raw evidence stays intact. Actual provenance/read rights
        # above are mandatory; these schema/DTO comparisons do not grant them.
        for step, stage, target in [
            (acquired.step.evidence, "started", acquired.step.controller.target),
            (ending.step.evidence, "closed", ending.step.target),
        ]:
            raw = self.evidence.read(step, control)
            if (
                len(raw) != step.size_bytes
                or hashlib.sha256(raw).hexdigest() != step.sha256
            ):
                raise EvidenceIntegrityError(
                    "Original full training kernel/controller bytes changed"
                )
            value = json_object(raw)
            if (
                value.get("schema_version") != "sft-step-raw/1"
                or value.get("phase") != stage
                or value.get("target") != target.model_dump(mode="json")
                or value.get("error") is not None
                or not value.get("kernel")
                or not value.get("commands")
            ):
                raise EvidenceIntegrityError(
                    "Original raw training step evidence incomplete/mismatched"
                )
        control.checkpoint()
