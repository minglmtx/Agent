"""Exact bodies during one parent proof; missing refs never fall back to I/O."""

import os
import threading
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_state_inputs import MapStateInputBodies
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceNotFound
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


class MapStateBodyReader:
    def __init__(self, bodies: MapStateInputBodies, control: OperationControl) -> None:
        bodies = MapStateInputBodies.model_validate(bodies)
        self._bodies = {b.reference: b.text.encode() for b in bodies.bodies}
        self._owner = os.getpid(), threading.get_ident()
        self._closed = False
        self.control = control
        self.read_count = 0

    def close(self) -> None:
        self._closed = True
        self._bodies.clear()

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        self.control.checkpoint()
        if self._closed or self._owner != (os.getpid(), threading.get_ident()):
            raise InvalidTransition("Map immutable input proof is no longer active")
        reference = EvidenceRef.model_validate(reference)
        try:
            raw = self._bodies[reference]
        except KeyError as error:
            raise EvidenceNotFound(
                "Reference outside the original Map input graph"
            ) from error
        require_complete_bytes(reference, raw)
        self.read_count += 1
        self.control.checkpoint()
        control.checkpoint()
        return raw
