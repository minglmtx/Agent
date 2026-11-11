"""Read public observation bytes and dependencies, shared by input consumers.

Typed content/identity checks replace merely checking whether a blob exists.
All I/O is bounded cooperatively; hard I/O interruption belongs to supervision.
"""

from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.verified_evidence import VerifiedEvidenceInputs
from lab_generate_skill.domain.observation_viewport import VIEWPORT_NAME
from .observation_viewports import read_public_viewport


class ObservationReader:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def _read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        value = self.store.read(reference, control=control)
        control.checkpoint()
        return value

    def resolve(
        self, observation: Observation, control: OperationControl
    ) -> ResolvedObservation:
        observation = Observation.model_validate(observation)
        control.checkpoint()
        text = observation.text
        if observation.text_ref is not None:
            try:
                text = self._read(observation.text_ref, control).decode("utf-8")
            except UnicodeDecodeError as error:
                raise EvidenceIntegrityError("Observation text is not UTF-8") from error
        for artifact in observation.artifacts:
            if artifact.name != VIEWPORT_NAME:
                self._read(artifact.reference, control)
        control.checkpoint()
        resolved = ResolvedObservation(record=observation, text=text)
        read_public_viewport(resolved, self.store, control)
        control.checkpoint()
        return resolved

    def load(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ResolvedObservation:
        reference = EvidenceRef.model_validate(reference)
        if (
            reference.visibility != "public"
            or reference.content_schema != "observation/1"
        ):
            raise ValueError("Expected public observation/1")
        observation = (
            self.store.read_document(
                reference, Observation, 16 * 1024**2, control, canonical=False
            )
            if isinstance(self.store, VerifiedEvidenceInputs)
            else Observation.model_validate_json(self._read(reference, control))
        )
        if type(observation) is not Observation:
            raise EvidenceIntegrityError("Observation reader changed its document type")
        return self.resolve(observation, control)

    def initial(
        self, context: PublicConstructionContext, control: OperationControl
    ) -> ResolvedObservation:
        context = PublicConstructionContext.model_validate(context)
        resolved = self.load(context.initial_observation_ref, control)
        resolved.record.check_initial(context.task.identity, context.context_id)
        return resolved
