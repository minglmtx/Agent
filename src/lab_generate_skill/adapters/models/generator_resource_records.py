"""Resource fact encoding and exact resource/operation acknowledgement checks."""

from lab_generate_skill.ports.lifecycle import OperationControl

import hashlib
import json
from typing import Any
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.ports.evidence import EvidenceStore


def phase(op: OperationContext, name: str) -> OperationContext:
    return OperationContext.model_validate(
        {
            **op.model_dump(),
            "operation_id": "generator-"
            + name
            + "-"
            + hashlib.sha256(op.operation_id.encode()).hexdigest(),
            "parent_operation_id": op.operation_id,
        }
    )


def check_operation(
    spec: GeneratorResourceSpec, op: OperationContext, mode: str
) -> None:
    token = spec.token
    if op.mode != mode or (
        op.run_id,
        op.owner_id,
        op.allocation_id,
        op.attempt_id,
        op.recovery_ref,
    ) != (
        token.owner.run_id,
        token.owner.owner_id,
        token.allocation_id,
        token.attempt_id,
        token.recovery_ref,
    ):
        raise OwnershipConflict(
            "Generator operation must address original batch allocation"
        )


def put(
    evidence: EvidenceStore, payload: bytes, schema: str, control: OperationControl
) -> EvidenceRef:
    return evidence.put(
        payload,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="fixed-generator-worker",
        ),
        control=control,
    )


def fact(
    evidence: EvidenceStore,
    spec: GeneratorResourceSpec,
    op: OperationContext,
    kind: str,
    details: dict[str, Any],
    control: OperationControl,
) -> EvidenceRef:
    return put(
        evidence,
        json.dumps(
            {
                "schema_version": "generator-resource-fact/1",
                "spec_sha256": hashlib.sha256(
                    spec.model_dump_json().encode()
                ).hexdigest(),
                "token": spec.token.model_dump(mode="json"),
                "operation": op.model_dump(mode="json"),
                "kind": kind,
                **details,
            },
            sort_keys=True,
        ).encode(),
        "generator-resource-fact/1",
        control=control,
    )


def acknowledged(
    record: ResourceRecord,
    spec: GeneratorResourceSpec,
    state: ResourceState,
    op: OperationContext,
    ref: EvidenceRef,
    revision: int,
) -> ResourceRecord:
    record = ResourceRecord.model_validate(record)
    if (
        record.token != spec.token
        or record.state != state
        or record.revision != revision
        or record.events[-1].operation != op
        or record.events[-1].evidence != (ref,)
    ):
        raise EvidenceIntegrityError(
            "Resource journal did not acknowledge original fact"
        )
    return record
