"""Same-call immutable CAS handoff for this fixed category proof, never rights."""

import os
import threading
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl

SCHEMAS = frozenset(
    {
        "task-binding/1",
        "shopping-category-navigation/1",
        "shopping-native-contract/1",
        "initial-state-spec/1",
        "site-resource-spec/1",
        "site-resource-started/1",
        "environment-selection/1",
        "shopping-category-recovery/1",
        "recovery-plan/1",
    }
)


class CategoryEvidenceBodies:
    def __init__(self, original: EvidenceReader) -> None:
        self.original = original
        self.owner = os.getpid(), threading.get_ident()
        self.closed = False
        self.bodies: dict[EvidenceRef, bytes] = {}
        self.bytes = 0

    def close(self) -> None:
        self.closed = True
        self.bodies.clear()

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        if self.closed or self.owner != (os.getpid(), threading.get_ident()):
            raise InvalidTransition(
                "Original category evidence call is no longer active"
            )
        reference = EvidenceRef.model_validate(reference)
        if reference in self.bodies:
            raw = self.bodies[reference]
        else:
            raw = self.original.read(reference, control)
            require_complete_bytes(reference, raw)
            if (
                reference.uri == "cas://sha256/" + reference.sha256
                and reference.content_schema in SCHEMAS
                and (reference.visibility, reference.media_type)
                == ("private", "application/json")
                and reference.size_bytes <= 1024**2
                and len(self.bodies) < 64
                and self.bytes + len(raw) <= 6 * 1024**2
            ):
                self.bodies[reference] = raw
                self.bytes += len(raw)
        control.checkpoint()
        return raw
