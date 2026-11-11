"""Optional bounded history handoff within one generation's verified carrier."""

from collections import OrderedDict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody


class ActorHistoryBodies:
    schemas = frozenset({"actor-model-response/1", "actor-parse-failure/1"})
    max_objects = 32
    max_bytes = 8 * 1024**2
    total_bytes = 64 * 1024**2

    def __init__(self) -> None:
        self._bodies: OrderedDict[EvidenceRef, VerifiedEvidenceBody] = OrderedDict()
        self._bytes = 0

    def clear(self) -> None:
        self._bodies.clear()
        self._bytes = 0

    def get(self, reference: EvidenceRef) -> VerifiedEvidenceBody | None:
        body = self._bodies.get(reference)
        if body is not None:
            self._bodies.move_to_end(reference)
        return body

    def reserve_primary(self, primary_bytes: int) -> None:
        while self._bodies and self._bytes + primary_bytes > self.total_bytes:
            _, old = self._bodies.popitem(last=False)
            self._bytes -= len(old.raw)

    def retain(self, body: VerifiedEvidenceBody, primary_bytes: int) -> None:
        size = len(body.raw)
        if size > min(self.max_bytes, self.total_bytes - primary_bytes):
            return  # Valid long history remains streamable; retention is optional.
        if body.reference in self._bodies:
            self._bodies.move_to_end(body.reference)
            return
        while self._bodies and (
            len(self._bodies) >= self.max_objects
            or self._bytes + size > self.max_bytes
            or self._bytes + size + primary_bytes > self.total_bytes
        ):
            _, old = self._bodies.popitem(last=False)
            self._bytes -= len(old.raw)
        self._bodies[body.reference] = body
        self._bytes += size
