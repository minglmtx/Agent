"""Check the supplied raw identity before independent live authority observations.

Matching bytes are not a live proof: the authority must still reread the original
kernel/controller state. Never interpret malformed/missing raw as an empty tree.
"""

import hashlib
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object


def require_step_raw(
    store: EvidenceReader,
    reference: EvidenceRef,
    target: SlurmStepTarget,
    phase: str,
    control: OperationControl,
) -> None:
    reference = EvidenceRef.model_validate(reference)
    target = SlurmStepTarget.model_validate(target)
    if phase not in ("started", "closed"):
        raise ValueError("Unsupported successful step evidence phase")
    if (reference.visibility, reference.content_schema) != (
        "private",
        "generator-step-raw/1",
    ) or not 0 < reference.size_bytes <= 64 * 1024 * 1024:
        raise EvidenceIntegrityError("Step authority requires bounded private raw")
    control.checkpoint()
    raw = store.read(reference, control=control)
    control.checkpoint()
    if (
        type(raw) is not bytes
        or len(raw) != reference.size_bytes
        or hashlib.sha256(raw).hexdigest() != reference.sha256
    ):
        raise EvidenceIntegrityError("Step raw identity differs")
    try:
        value = json_object(raw)
    except (ValueError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid step raw JSON") from error
    if (
        (value.get("schema_version"), value.get("phase"), value.get("target"))
        != (
            "generator-step-raw/1",
            phase,
            target.model_dump(mode="json"),
        )
        or "error" not in value
        or value["error"] is not None
    ):
        raise EvidenceIntegrityError(
            "Step raw does not describe the supplied successful phase"
        )
    if any(
        type(value.get(k)) is not list or not value[k] for k in ("kernel", "commands")
    ):
        raise EvidenceIntegrityError("Step raw omits kernel/controller observations")
    control.checkpoint()
