"""Same-call preparation bodies; native files and live authority stay original."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


class MapPreparationBodies:
    def __init__(
        self,
        original: EvidenceReader,
        inputs: PreparationInputs,
        private_spec: bytes | None,
        snapshot: bytes | None,
    ) -> None:
        self.original = original
        self.bodies: dict[EvidenceRef, bytes] = {}
        for reference, raw in (
            (inputs.binding.private_spec_ref, private_spec),
            (inputs.request.snapshot_ref, snapshot),
        ):
            if raw is not None:
                if reference is None:
                    raise ValueError("Preparation body needs its original reference")
                require_complete_bytes(reference, raw)
                self.bodies[reference] = raw

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        if reference in self.bodies:
            return self.bodies[reference]
        return self.original.read(reference, control=control)
