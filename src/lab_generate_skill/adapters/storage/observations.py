"""Publish/read immutable captured facts; no capture, retries or browser handles."""

from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import (
    Observation,
    ResolvedObservation,
    ObservationCommitUnconfirmed,
)
from copy import copy
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.lifecycle import OperationControls


class EvidenceObservations:
    def __init__(self, store: EvidenceStore, controls: OperationControls) -> None:
        self.store, self.controls = store, controls
        self.reader = ObservationReader(store)

    def with_inputs(self, inputs: EvidenceReader) -> ObservationLoader:
        reader = copy(self)
        reader.reader = ObservationReader(inputs)
        return reader

    def publish(self, observation: Observation, op: OperationContext) -> EvidenceRef:
        observation = Observation.model_validate(observation)
        op = OperationContext.model_validate(op)
        if op.mode != "execute" or op.attempt_id != observation.attempt_id:
            raise OwnershipConflict(
                "Observation publication requires its attempt execute operation"
            )
        control = self.controls.bind(op)
        self.reader.resolve(observation, control)
        control.checkpoint()
        reference = self.store.put(
            observation.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="observation/1",
                visibility="public",
                producer="observation-records-v1",
            ),
            control=control,
        )
        try:
            control.checkpoint()
        except Exception as error:
            raise ObservationCommitUnconfirmed(reference) from error
        return reference

    def load(self, reference: EvidenceRef, op: OperationContext) -> ResolvedObservation:
        op = OperationContext.model_validate(op)
        result = self.reader.load(reference, self.controls.bind(op))
        if op.attempt_id is not None and op.attempt_id != result.record.attempt_id:
            raise OwnershipConflict("Observation belongs to another attempt")
        return result
