"""Read the original browser ending; never signal, restore or create a receipt."""

import hashlib
import json
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)


def original_closed_browser(
    spec: BrowserResourceSpec,
    acquisition: OperationContext,
    operation: OperationContext,
    journal: ResourceJournal,
    evidence: EvidenceReader,
    control: OperationControl,
) -> ResourceRecord:
    control.checkpoint()
    record = ResourceRecord.model_validate(journal.read(spec.token, operation))
    if (
        record.token != spec.token
        or record.state != "closed"
        or len(record.events) < 4
        or record.events[1].state != "acquiring"
        or record.events[1].operation != acquisition
        or len(record.events[1].evidence) != 1
        or len(record.events[-1].evidence) != 1
    ):
        raise OwnershipConflict("Original browser closure has not been confirmed")

    def read(reference: EvidenceRef, schema: str) -> bytes:
        if (reference.content_schema, reference.visibility, reference.media_type) != (
            schema,
            "private",
            "application/json",
        ):
            raise OwnershipConflict("Original browser ending schema/visibility changed")
        require_complete_read_bound(reference, 64 * 1024**2)
        raw = evidence.read(reference, control=control)
        require_complete_bytes(reference, raw)
        control.checkpoint()
        return raw

    intent = ResourceAcquisitionIntent.model_validate_json(
        read(record.events[1].evidence[0], "resource-acquisition-intent/1")
    )
    if (intent.token, intent.operation, intent.configuration_ref.sha256) != (
        spec.token,
        acquisition,
        hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
    ):
        raise OwnershipConflict("Browser closure changed original acquisition")
    ending = json.loads(read(record.events[-1].evidence[0], "browser-resource-fact/1"))
    if (
        ending["schema_version"],
        ending["token"],
        ending["spec_sha256"],
        ending["operation"],
        ending["state"],
    ) != (
        "browser-resource-fact/1",
        spec.token.model_dump(mode="json"),
        intent.configuration_ref.sha256,
        record.events[-1].operation.model_dump(mode="json"),
        "closed",
    ) or ending[
        "details"
    ][
        "cleanup_errors"
    ]:
        raise OwnershipConflict(
            "Browser ending differs from its original complete record"
        )
    closure = ClosureReceipt.model_validate_json(
        json.dumps(ending["details"]["closure"])
    )
    if (
        closure.token != spec.token
        or closure.status != "closed"
        or closure.primary_error is not None
        or record.events[-1].operation.parent_operation_id != closure.operation_id
    ):
        raise OwnershipConflict("Original complete-resource browser closure required")
    control.checkpoint()
    return record
