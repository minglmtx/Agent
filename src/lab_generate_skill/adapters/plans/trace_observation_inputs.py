"""Original typed observation resolution, with same-trace fact handoff only."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.trace_body_inputs import TraceObservationInputReads
from .observations import ObservationReader


class TraceObservationReader(ObservationReader):
    def load(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ResolvedObservation:
        reference = EvidenceRef.model_validate(reference)
        if (
            reference.visibility != "public"
            or reference.content_schema != "observation/1"
        ):
            raise ValueError("Expected public observation/1")
        if isinstance(self.store, TraceObservationInputReads):
            known = self.store.observation_inputs(reference, control)
            if known is not None:
                return known
        result = super().load(reference, control)
        if isinstance(self.store, TraceObservationInputReads):
            self.store.observed_inputs(reference, result, control)
        return result
