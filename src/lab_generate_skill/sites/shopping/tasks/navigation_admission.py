"""Canonical category task and persisted original snapshot, without authority."""

import hashlib
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from .navigation_recovery import CategoryNavigationRecoverySnapshot
from .navigation_state import CategoryNavigationExecutionInput


def task_input(request: SiteTaskRequest) -> CategoryNavigationExecutionInput:
    data = CategoryNavigationExecutionInput.model_validate_json(request.private_input)
    if (
        data.model_dump_json() != request.private_input
        or data.spec.task != request.task
    ):
        raise OwnershipConflict("Category native input changed canonical task binding")
    return data


def same_snapshot(
    request: SiteTaskRequest,
    snapshot: CategoryNavigationRecoverySnapshot,
    original_ref: EvidenceRef | None,
) -> EvidenceRef:
    old = snapshot.request
    if any(
        getattr(old, k) != getattr(request, k)
        for k in ("task", "binding_ref", "private_input")
    ) or any(
        getattr(old.operation, k) != getattr(request.operation, k)
        for k in ("run_id", "owner_id", "attempt_id", "allocation_id", "recovery_ref")
    ):
        raise OwnershipConflict("Category task changed original snapshot scope")
    raw, ref = snapshot.model_dump_json().encode(), request.snapshot_ref
    if (
        ref is None
        or (ref.content_schema, ref.sha256, ref.size_bytes)
        != (snapshot.schema_version, hashlib.sha256(raw).hexdigest(), len(raw))
        or (original_ref is not None and ref != original_ref)
    ):
        raise OwnershipConflict("Category task lost original persisted snapshot bytes")
    return ref
