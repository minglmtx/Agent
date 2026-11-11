"""Original resource facts and wire bytes on the existing controlled CAS port."""

import hashlib
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


def metadata(schema: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="fixed-sft-resource-v1",
    )


def put_raw(
    evidence: EvidenceStore, raw: bytes, schema: str, control: OperationControl
) -> EvidenceRef:
    expected = evidence_reference(raw, metadata(schema))
    control.checkpoint()
    try:
        actual = evidence.put(raw, metadata(schema), control)
        if actual != expected or evidence.read(expected, control) != raw:
            raise EvidenceIntegrityError(
                "Original training resource publication/readback changed"
            )
        control.checkpoint()
        return expected
    except BaseException as error:
        setattr(error, "training_resource_reference", expected)
        raise


def put(
    evidence: EvidenceStore, value: Contract, control: OperationControl
) -> EvidenceRef:
    schema = value.model_dump().get("schema_version")
    if type(schema) is not str:
        raise ValueError("Original versioned training resource document required")
    return put_raw(evidence, value.model_dump_json().encode(), schema, control)


def phase(op: OperationContext, name: str) -> OperationContext:
    return OperationContext.model_validate(
        {
            **op.model_dump(),
            "operation_id": "sft-"
            + name
            + "-"
            + hashlib.sha256(op.operation_id.encode()).hexdigest(),
            "parent_operation_id": op.operation_id,
        }
    )


def acknowledged(
    record: ResourceRecord,
    token: object,
    state: ResourceState,
    op: OperationContext,
    ref: EvidenceRef,
    revision: int,
) -> ResourceRecord:
    record = ResourceRecord.model_validate(record)
    if (
        record.token,
        record.state,
        record.revision,
        record.events[-1].operation,
        record.events[-1].evidence,
    ) != (token, state, revision, op, (ref,)):
        raise EvidenceIntegrityError(
            "Training resource journal did not acknowledge exact original fact"
        )
    return record
