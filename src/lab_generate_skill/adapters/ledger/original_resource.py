"""Bound read-only original resource CAS primitives; no create, retry or permission."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


@dataclass(frozen=True)
class BoundOriginalReadControls:
    operation: OperationContext
    control: OperationControl

    def bind(self, operation: OperationContext) -> OperationControl:
        if operation != self.operation:
            raise OwnershipConflict("Original journal read changed its bound operation")
        return self.control


class OriginalResourceFacts:
    def __init__(self, root: str, role: Literal["site", "browser"]) -> None:
        if role not in ("site", "browser"):
            raise ValueError("Fixed original resource role required")
        self.role = role
        self.store = FileEvidenceStore(Path(root), initialize=False)

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        if (reference.visibility, reference.media_type, reference.producer) != (
            "private",
            "application/json",
            "fixed-" + self.role + "-resource",
        ) or not 0 < reference.size_bytes <= 16 * 1024 * 1024:
            raise EvidenceIntegrityError(
                f"Original small private {self.role} acquisition fact required"
            )
        control.checkpoint()
        raw = self.store.read(reference)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            reference.size_bytes,
            reference.sha256,
        ):
            raise EvidenceIntegrityError(
                f"Original {self.role} acquisition bytes changed"
            )
        control.checkpoint()
        return raw

    def fact(
        self,
        reference: EvidenceRef,
        model: type[T],
        schema: str,
        control: OperationControl,
    ) -> T:
        if reference.content_schema != schema:
            raise EvidenceIntegrityError(
                f"Original {self.role} acquisition schema changed"
            )
        raw = self.read(reference, control)
        json_object(raw)
        return model.model_validate_json(raw)
