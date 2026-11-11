"""Read complete original site closure, including its acquisition and raw fact."""

import hashlib
import json
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.policies.evidence_bytes import (
    require_complete_bytes,
    require_complete_read_bound,
)


def original_closed_site(
    spec: SiteResourceSpec,
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
        raise OwnershipConflict(
            "Original complete-resource site closure is unconfirmed"
        )

    def read(ref: EvidenceRef, schema: str) -> bytes:
        if (ref.content_schema, ref.visibility, ref.media_type) != (
            schema,
            "private",
            "application/json",
        ):
            raise OwnershipConflict("Original site ending schema/visibility changed")
        require_complete_read_bound(ref, 64 * 1024**2)
        raw = evidence.read(ref, control=control)
        require_complete_bytes(ref, raw)
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
        raise OwnershipConflict("Site ending changed original acquisition")
    # Verify the original full configuration, not just a descriptor comparison.
    if (
        read(intent.configuration_ref, spec.schema_version)
        != spec.model_dump_json().encode()
    ):
        raise OwnershipConflict("Site ending changed original configuration bytes")
    ending = json.loads(read(record.events[-1].evidence[0], "site-resource-fact/1"))
    if (
        ending["schema_version"],
        ending["token"],
        ending["spec_sha256"],
        ending["operation"],
        ending["state"],
    ) != (
        "site-resource-fact/1",
        spec.token.model_dump(mode="json"),
        intent.configuration_ref.sha256,
        record.events[-1].operation.model_dump(mode="json"),
        "closed",
    ) or ending[
        "details"
    ][
        "cleanup_errors"
    ]:
        raise OwnershipConflict("Site ending differs from original complete record")
    closure = ClosureReceipt.model_validate_json(
        json.dumps(ending["details"]["closure"])
    )
    if (
        closure.token != spec.token
        or closure.status != "closed"
        or closure.primary_error is not None
        or record.events[-1].operation.parent_operation_id != closure.operation_id
    ):
        raise OwnershipConflict("Original complete-resource site closure required")
    # details.primary records the consumer/start failure independently; it is
    # preserved by the original manager and is not a cleanup success predicate.
    control.checkpoint()
    return record
