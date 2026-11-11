"""Pure original-task and persisted-snapshot checks; no execution authority."""

import hashlib
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from .image_spec import NativeImageSpec


def task_input(request: SiteTaskRequest) -> NativeImageSpec:
    value = NativeImageSpec.model_validate_json(request.private_input)
    if value.model_dump_json() != request.private_input or value.task != request.task:
        raise OwnershipConflict("Reddit private input changed original canonical task")
    return value


def same_task(request: SiteTaskRequest, original: SiteTaskRequest) -> None:
    if (request.task, request.binding_ref, request.private_input) != (
        original.task,
        original.binding_ref,
        original.private_input,
    ):
        raise OwnershipConflict("Reddit operation changed original task/binding/input")
    for name in ("run_id", "owner_id", "attempt_id", "allocation_id", "recovery_ref"):
        if getattr(request.operation, name) != getattr(original.operation, name):
            raise OwnershipConflict(
                "Reddit operation changed original allocation/recovery"
            )


def snapshot_reference(
    request: SiteTaskRequest,
    original: SiteTaskRequest,
    raw: bytes,
    schema: str,
    previous: EvidenceRef | None,
) -> EvidenceRef:
    same_task(request, original)
    ref = request.snapshot_ref
    if (
        ref is None
        or (ref.content_schema, ref.sha256, ref.size_bytes)
        != (schema, hashlib.sha256(raw).hexdigest(), len(raw))
        or (previous is not None and ref != previous)
    ):
        raise OwnershipConflict(
            "Reddit operation lost original persisted snapshot bytes"
        )
    return ref
