"""Exact bytes just published by one original browser step; no dispatch right."""

from dataclasses import dataclass
from lab_generate_skill.domain.browser import StepResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class PublishedStepInputs:
    result: StepResult
    bodies: tuple[VerifiedEvidenceBody, VerifiedEvidenceBody, VerifiedEvidenceBody]
    remaining: EvidenceReader

    def __post_init__(self) -> None:
        if tuple(body.reference for body in self.bodies) != (
            self.result.before_observation_ref,
            self.result.return_ref,
            self.result.observation_ref,
        ):
            raise OwnershipConflict("Published step changed complete return references")

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        for body in self.bodies:
            if reference == body.reference:
                return body.raw
            if reference.uri == body.reference.uri:
                raise OwnershipConflict("Published step reference metadata changed")
        # Other declared evidence (e.g. action recovery and observation assets)
        # still uses its real storage authority. This never builds missing data.
        return self.remaining.read(reference, control=control)
