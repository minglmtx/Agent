"""Persist bounded step/kernel raw facts, retaining expected identity on failure."""

from lab_generate_skill.ports.lifecycle import OperationControl

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.slurm.step_evidence import encode_step_raw
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture


def save_step_raw(
    store: EvidenceStore,
    target: SlurmStepTarget | None,
    phase: str,
    kernels: list[KernelCapture],
    commands: list[CommandCapture],
    error: BaseException | None = None,
    *,
    control: OperationControl,
) -> EvidenceRef:
    raw = encode_step_raw("actor-step-raw/1", target, phase, kernels, commands, error)
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema="actor-step-raw/1",
        visibility="private",
        producer="fixed-actor-step-v1",
    )
    expected = evidence_reference(raw, metadata)
    try:
        result = store.put(raw, metadata, control=control)
        if result != expected:
            raise ValueError("Step evidence store returned a different identity")
        return result
    except BaseException as failure:
        setattr(failure, "actor_step_evidence_ref", expected)
        raise
