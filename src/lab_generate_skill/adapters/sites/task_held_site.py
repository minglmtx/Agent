"""Read original acquired site binding for current task ports, without any effect."""

from uuid import uuid4
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_preparation import RecordedSiteTaskPreparation


def original_acquired_task_site(
    preparation: RecordedSiteTaskPreparation,
    operation: OperationContext,
    control: OperationControl,
) -> ResourceRecord:
    p, cfg = preparation, preparation.spec.configuration
    reads = StateReads(p.io.store)
    control.checkpoint()
    original = p.state.original_acquired()
    read = operation.model_copy(
        update={
            "operation_id": "held-task-site-" + uuid4().hex,
            "parent_operation_id": p.declaration.resource_read_operation.parent_operation_id,
            "mode": "cleanup",
            "attempt_id": None,
            "allocation_id": cfg.token.allocation_id,
            "recovery_ref": cfg.token.recovery_ref,
            "cancellation_ref": None,
        }
    )
    record = ResourceRecord.model_validate(p.resources.read(cfg.token, read))
    if (
        record.token != cfg.token
        or record.state != "acquired"
        or len(record.events) != 3
        or len(record.events[1].evidence) != 1
        or len(record.events[2].evidence) != 1
        or p.state.acquired_ref is None
    ):
        raise OwnershipConflict("Original site is not the same acquired resource")
    intent = reads.parse(
        record.events[1].evidence[0],
        "resource-acquisition-intent/1",
        ResourceAcquisitionIntent,
        control,
    )
    bound = reads.parse(
        p.state.acquired_ref, "site-task-acquired/1", SiteTaskAcquired, control
    )
    spec = reads.parse(
        p.declaration.site_spec_ref, "site-resource-spec/1", SiteResourceSpec, control
    )
    started = reads.parse(
        bound.site_started_ref, "site-resource-started/1", SiteResourceStarted, control
    )
    if (
        bound != original
        or bound.declaration_ref != p.plan.declaration_ref
        or bound.resource_intent_ref != record.events[1].evidence[0]
        or bound.resource_acquired_ref != record.events[2].evidence[0]
        or intent.token != cfg.token
        or intent.configuration_ref != p.declaration.site_spec_ref
        or intent.operation.operation_id != read.parent_operation_id
        or spec != p.spec
        or started != p.site.site
        or started.instance.files != cfg.files
    ):
        raise OwnershipConflict(
            "Original site acquisition, configuration or owner binding changed"
        )
    control.checkpoint()
    return record
