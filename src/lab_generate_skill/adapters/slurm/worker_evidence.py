"""Private role-bound step facts, including partial failures; no execution rights."""

from lab_generate_skill.adapters.slurm.step_evidence import encode_step_raw
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    retained_capture,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)


from typing import Literal


class WorkerStepEvidence:
    def __init__(self, role: Literal["browser", "site"]) -> None:
        if role not in ("browser", "site"):
            raise ValueError("Unsupported fixed worker role")
        self.role = role
        self.schema = role + "-step-raw/1"
        self.producer = "fixed-" + role + "-step-v1"
        self.error_attribute = role + "_step_evidence_ref"

    def require(
        self,
        store: EvidenceReader,
        reference: EvidenceRef,
        target: SlurmStepTarget,
        phase: Literal["ready", "started", "closed"],
        control: OperationControl,
    ) -> None:
        """Bind supplied raw bytes before independent original live inspection.

        This validates an observation envelope, never its truth or permission.
        """
        reference = EvidenceRef.model_validate(reference)
        target = SlurmStepTarget.model_validate(target)
        if phase not in ("ready", "started", "closed"):
            raise ValueError("Successful original worker phase required")
        if (
            reference.visibility,
            reference.content_schema,
            reference.media_type,
            reference.producer,
        ) != ("private", self.schema, "application/json", self.producer):
            raise EvidenceIntegrityError("Original role-bound worker raw required")
        require_complete_read_bound(reference, 64 * 1024**2)
        control.checkpoint()
        raw = store.read(reference, control=control)
        require_complete_bytes(reference, raw)
        try:
            value = json_object(raw)
        except (ValueError, RecursionError) as error:
            raise EvidenceIntegrityError("Invalid worker raw JSON") from error
        if (
            (value.get("schema_version"), value.get("phase"), value.get("target"))
            != (self.schema, phase, target.model_dump(mode="json"))
            or "error" not in value
            or value["error"] is not None
            or any(
                type(value.get(k)) is not list or not value[k]
                for k in ("kernel", "commands")
            )
        ):
            raise EvidenceIntegrityError("Incomplete or mismatched worker raw")
        control.checkpoint()

    def save(
        self,
        store: EvidenceStore,
        target: SlurmStepTarget | None,
        phase: str,
        kernels: list[KernelCapture],
        commands: list[CommandCapture],
        control: OperationControl,
        error: BaseException | None = None,
    ) -> EvidenceRef:
        raw = encode_step_raw(self.schema, target, phase, kernels, commands, error)
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=self.schema,
            visibility="private",
            producer=self.producer,
        )
        expected = evidence_reference(raw, metadata)
        try:
            actual = store.put(raw, metadata, control=control)
            if actual != expected:
                raise ValueError("Worker step evidence changed original identity")
            return actual
        except BaseException as failure:
            setattr(failure, self.error_attribute, expected)
            raise

    def retain_failure(
        self,
        store: EvidenceStore,
        target: SlurmStepTarget | None,
        phase: str,
        kernels: list[KernelCapture],
        commands: list[CommandCapture],
        error: BaseException,
        *,
        metadata_control: OperationControl | None = None,
    ) -> None:
        pending = [error]
        while pending:
            failure = pending.pop(0)
            kernel = getattr(failure, "slurm_kernel_capture", None)
            if isinstance(kernel, KernelCapture) and not any(
                k is kernel for k in kernels
            ):
                kernels.append(kernel)
            for capture in getattr(failure, "slurm_step_commands", ()):
                if not any(c is capture for c in commands):
                    commands.append(capture)
            capture = retained_capture(failure)
            if capture is not None and not any(c is capture for c in commands):
                commands.append(capture)
            if isinstance(failure, BaseExceptionGroup):
                pending[0:0] = failure.exceptions
        if hasattr(error, self.error_attribute):
            return
        try:
            ref = self.save(
                store,
                target,
                phase,
                kernels,
                commands,
                (
                    metadata_control
                    if metadata_control is not None
                    else DeadlineControl(5, self.role + "-step-diagnostic")
                ),
                error,
            )
        except BaseException as storage:
            combined = BaseExceptionGroup(
                "Worker step observation and evidence failed", [error, storage]
            )
            if hasattr(storage, self.error_attribute):
                setattr(
                    combined,
                    self.error_attribute,
                    getattr(storage, self.error_attribute),
                )
            raise combined from None
        setattr(error, self.error_attribute, ref)

    def diagnostic_candidates(
        self, errors: list[BaseException]
    ) -> tuple[EvidenceRef, ...]:
        """Known addresses may have lost publication acknowledgements, not proof of writes."""
        references: list[EvidenceRef] = []
        pending = list(errors)
        while pending:
            failure = pending.pop(0)
            reference = getattr(failure, self.error_attribute, None)
            if isinstance(reference, EvidenceRef) and reference not in references:
                references.append(reference)
            if isinstance(failure, BaseExceptionGroup):
                pending[0:0] = failure.exceptions
        return tuple(references)
