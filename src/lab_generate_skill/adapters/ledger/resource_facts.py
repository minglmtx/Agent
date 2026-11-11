"""Browser resource evidence and exact existing-journal acknowledgements."""

from typing import Literal, Protocol
from lab_generate_skill.domain.lifecycle import AllocationToken
import hashlib
import json
from typing import Any
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


class ResourceSpecification(Protocol):
    @property
    def token(self) -> AllocationToken: ...
    def model_dump_json(self) -> str: ...


class ResourceFacts:
    def __init__(self, role: Literal["browser", "site"]) -> None:
        if role not in ("browser", "site"):
            raise ValueError("Unsupported fixed resource role")
        self.role = role

    def phase(self, operation: OperationContext, name: str) -> OperationContext:
        return OperationContext.model_validate(
            {
                **operation.model_dump(),
                "operation_id": self.role
                + "-"
                + name
                + "-"
                + hashlib.sha256(operation.operation_id.encode()).hexdigest(),
                "parent_operation_id": operation.operation_id,
            }
        )

    def put(
        self, store: EvidenceStore, data: bytes, schema: str, control: OperationControl
    ) -> EvidenceRef:
        return store.put(data, self.metadata(schema), control=control)

    def metadata(self, schema: str) -> EvidenceMetadata:
        return EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="fixed-" + self.role + "-resource",
        )

    def reference(self, data: bytes, schema: str) -> EvidenceRef:
        """Exact original publisher identity; bytes/hash alone are insufficient."""
        return evidence_reference(data, self.metadata(schema))

    @staticmethod
    def encode(data: dict[str, Any]) -> bytes:
        """Original resource-fact producer bytes, including sorting and spacing."""
        return json.dumps(data, sort_keys=True).encode()

    def fact(
        self,
        store: EvidenceStore,
        spec: ResourceSpecification,
        operation: OperationContext,
        state: ResourceState,
        details: dict[str, Any],
        control: OperationControl,
    ) -> EvidenceRef:
        data = {
            "schema_version": self.role + "-resource-fact/1",
            "spec_sha256": hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
            "token": spec.token.model_dump(mode="json"),
            "operation": operation.model_dump(mode="json"),
            "state": state,
            "details": details,
        }
        return self.put(
            store,
            self.encode(data),
            self.role + "-resource-fact/1",
            control,
        )

    def acknowledged(
        self,
        record: ResourceRecord,
        spec: ResourceSpecification,
        state: ResourceState,
        operation: OperationContext,
        reference: EvidenceRef,
        revision: int,
    ) -> ResourceRecord:
        record = ResourceRecord.model_validate(record)
        if (
            record.token,
            record.state,
            record.revision,
            record.events[-1].operation,
            record.events[-1].evidence,
        ) != (spec.token, state, revision, operation, (reference,)):
            raise EvidenceIntegrityError(
                "Resource journal did not acknowledge the original fact"
            )
        return record
