"""Original task/snapshot identity checks shared by the two registered families."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict


def same_native_snapshot(
    request: SiteTaskRequest,
    original: SiteTaskRequest,
    raw: bytes,
    schema: str,
    original_ref: EvidenceRef | None,
    label: str,
) -> EvidenceRef:
    if (request.task, request.binding_ref, request.private_input) != (
        original.task,
        original.binding_ref,
        original.private_input,
    ):
        raise OwnershipConflict(
            label + " operation changed original snapshot task/binding"
        )
    for name in ("run_id", "owner_id", "attempt_id", "allocation_id", "recovery_ref"):
        if getattr(request.operation, name) != getattr(original.operation, name):
            raise OwnershipConflict(
                label + " operation changed original snapshot allocation/recovery"
            )
    ref = request.snapshot_ref
    if (
        ref is None
        or (ref.content_schema, ref.sha256, ref.size_bytes)
        != (schema, hashlib.sha256(raw).hexdigest(), len(raw))
        or (original_ref is not None and ref != original_ref)
    ):
        raise OwnershipConflict(
            label + " operation lost original persisted snapshot bytes"
        )
    return ref
