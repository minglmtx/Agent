"""Private raw allocation diagnostics, independent of query/orchestration.

Known expected CAS identity does not prove publication. Preserve it on storage
failure so callers can inspect the original evidence without repeating work.
This uses the current synchronous EvidenceStore inside external supervision;
it does not claim a hard storage deadline or production permission.
"""

from lab_generate_skill.ports.lifecycle import OperationControl

import base64
from dataclasses import asdict
import json

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.scheduler import (
    SlurmExecutionIdentity,
    SlurmJobObservation,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from .commands import CommandCapture
from .kernel_capture import KernelCapture


def save_allocation_evidence(
    store: EvidenceStore,
    execution: SlurmExecutionIdentity,
    writer: ProcessIdentity,
    op: OperationContext,
    commands: list[CommandCapture],
    kernels: list[KernelCapture],
    schedulers: list[SlurmJobObservation],
    stage: str,
    error: BaseException | None,
    scheduler_failure: EvidenceRef | None,
    control: OperationControl,
) -> EvidenceRef:
    payload = {
        "schema_version": "slurm-allocation-raw/1",
        "execution": execution.model_dump(mode="json"),
        "writer": writer.model_dump(mode="json"),
        "operation": op.model_dump(mode="json"),
        "stage": stage,
        "error_type": type(error).__name__ if error is not None else None,
        "scheduler_observations": [s.model_dump(mode="json") for s in schedulers],
        "scheduler_failure": (
            scheduler_failure.model_dump(mode="json")
            if scheduler_failure is not None
            else None
        ),
        "commands": [
            {
                "argv": c.argv,
                "returncode": c.returncode,
                "complete": c.complete,
                "stdout_base64": base64.b64encode(c.stdout).decode("ascii"),
                "stderr_base64": base64.b64encode(c.stderr).decode("ascii"),
                "termination": (
                    asdict(c.termination) if c.termination is not None else None
                ),
            }
            for c in commands
        ],
        "kernel_observations": [
            {
                "reads": [
                    {
                        "path": r.path,
                        "complete": r.complete,
                        "content_base64": base64.b64encode(r.content).decode("ascii"),
                    }
                    for r in k.reads
                ],
                "controls": [asdict(c) for c in k.controls],
                "failed_control_path": k.failed_control_path,
            }
            for k in kernels
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema="slurm-allocation-raw/1",
        visibility="private",
        producer="slurm-allocation-observer-v1",
    )
    expected = evidence_reference(raw, metadata)
    try:
        actual = store.put(raw, metadata, control=control)
        if actual != expected:
            raise ValueError(
                "Allocation evidence store returned a different content identity"
            )
    except BaseException as failure:
        setattr(failure, "slurm_allocation_evidence_ref", expected)
        raise
    return actual
