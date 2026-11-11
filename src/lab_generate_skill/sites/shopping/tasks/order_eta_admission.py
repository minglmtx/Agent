"""Pure original task/private payload/snapshot-reference binding, no authority."""

import hashlib
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from .order_eta_recovery import OrderEtaRecoverySnapshot
from .order_eta_state import OrderEtaExecutionInput


def task_input(request: SiteTaskRequest) -> OrderEtaExecutionInput:
    data = OrderEtaExecutionInput.model_validate_json(request.private_input)
    if (
        data.model_dump_json() != request.private_input
        or data.spec.task != request.task
    ):
        raise OwnershipConflict("Shopping task input changed canonical private task")
    return data


def same_snapshot(
    request: SiteTaskRequest,
    snapshot: OrderEtaRecoverySnapshot,
    original_ref: EvidenceRef | None,
) -> EvidenceRef:
    old = snapshot.request
    for key in ("task", "binding_ref", "private_input"):
        if getattr(old, key) != getattr(request, key):
            raise OwnershipConflict(
                "Shopping task changed original snapshot input/binding"
            )
    for key in ("run_id", "owner_id", "attempt_id", "allocation_id", "recovery_ref"):
        if getattr(old.operation, key) != getattr(request.operation, key):
            raise OwnershipConflict(
                "Shopping task changed original snapshot allocation/recovery"
            )
    raw, ref = snapshot.model_dump_json().encode(), request.snapshot_ref
    if (
        ref is None
        or (ref.content_schema, ref.sha256, ref.size_bytes)
        != (snapshot.schema_version, hashlib.sha256(raw).hexdigest(), len(raw))
        or (original_ref is not None and ref != original_ref)
    ):
        raise OwnershipConflict("Shopping task lost original persisted snapshot bytes")
    return ref
