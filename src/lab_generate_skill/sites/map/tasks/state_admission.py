"""Original task/recovery and complete-state bindings shared by concrete codecs."""

import hashlib
from typing import Literal
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_state_artifact import (
    MapStateArtifact,
    check_state_plan,
)


def same_task(request: SiteTaskRequest, original: SiteTaskRequest) -> None:
    if (request.task, request.binding_ref, request.private_input) != (
        original.task,
        original.binding_ref,
        original.private_input,
    ):
        raise OwnershipConflict("Map operation changed original task/binding/input")
    for name in ("run_id", "owner_id", "attempt_id", "allocation_id", "recovery_ref"):
        if getattr(request.operation, name) != getattr(original.operation, name):
            raise OwnershipConflict(
                "Map operation changed original allocation/recovery"
            )


def snapshot_reference(
    request: SiteTaskRequest,
    original: SiteTaskRequest,
    raw: bytes,
    previous: EvidenceRef | None,
    *,
    schema_version: Literal["map-overlay-snapshot/1", "map-navigation-snapshot/1"],
) -> EvidenceRef:
    same_task(request, original)
    ref = request.snapshot_ref
    if (
        ref is None
        or (ref.content_schema, ref.sha256, ref.size_bytes)
        != (schema_version, hashlib.sha256(raw).hexdigest(), len(raw))
        or previous is not None
        and ref != previous
    ):
        raise OwnershipConflict("Map operation lost original persisted snapshot bytes")
    return ref


def check_native(native: MapStateArtifact, request: SiteTaskRequest) -> None:
    check_state_plan(native.plan, request)
    if native.request_sha256 != request.digest:
        raise ValueError("Complete Map state artifact changed original task/resource")
