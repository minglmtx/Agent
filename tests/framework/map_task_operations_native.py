"""Persist the selected Map task intent once before its existing worker dispatch."""

from datetime import datetime, timezone, timedelta
from typing import Literal
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from map_qualified_source_native import MapQualifiedSource
from map_site_engineering_authority import MapEngineeringAuthority


def execute(
    source: MapQualifiedSource,
    action: Literal["snapshot", "prepare", "restore"],
    snapshot: EvidenceRef | None,
) -> tuple[SiteTaskRequest, SiteTaskResult]:
    if action not in ("snapshot", "prepare", "restore"):
        raise ValueError("Selected Map lifecycle operation required")
    n, c = source.native, source.c
    authority = c.authority
    if not isinstance(authority, MapEngineeringAuthority):
        raise OwnershipConflict("Original Map engineering resource authority required")
    seconds = 1200 if action in ("snapshot", "restore") else 600
    if action == "restore":
        if n.request is None or not source.saved.get("browser_closed_before_restore"):
            raise OwnershipConflict(
                "Original preparation and closed browser required before Map restore"
            )
        op = n.request.operation.cleanup(
            "native-task-restore", now=datetime.now(timezone.utc), seconds=seconds
        )
        closed = ClosureReceipt.model_validate_json(
            c.evidence.read(
                source.saved["browser_closure_ref"], control=c.controls.bind(op)
            )
        )
        if closed.status != "closed" or closed.token != source.browser_token:
            raise OwnershipConflict(
                "Map restore requires its exact declared browser closure"
            )
    else:
        op = c.op.model_copy(
            update={
                "operation_id": "native-task-" + action,
                "attempt_id": n.attempt_id,
                "recovery_ref": n.recovery_ref,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=seconds),
            }
        )
    request = SiteTaskRequest(
        task=n.public.identity,
        binding_ref=n.binding_ref,
        operation=op,
        action=action,
        snapshot_ref=snapshot,
        private_input=n.private_input_json(),
    )
    if op.operation_id in authority.task_intents:
        raise OwnershipConflict("Original Map task operation was already declared")
    authority.task_intents[op.operation_id] = n.put(request)
    result = source.site.tasks.execute_task(request, control=c.controls.bind(op))
    if result.request_sha256 != request.digest:
        raise OwnershipConflict("Map task returned another request")
    return request, result
