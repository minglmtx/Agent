"""Bounded public artifact resolution; no current browser or model operations."""

from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    viewport_reference,
)
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


def read_public_viewport(
    observed: ResolvedObservation,
    evidence: EvidenceReader | None,
    control: OperationControl,
) -> ObservationViewport | None:
    control.checkpoint()
    reference = viewport_reference(observed.record)
    if reference is None:
        return None
    if evidence is None:
        raise EvidenceIntegrityError(
            "Measured viewport consumer requires its artifact reader"
        )
    body = VerifiedEvidenceBody(reference, evidence.read(reference, control))
    result = ObservationViewport.model_validate_json(body.raw)
    if result.model_dump_json().encode() != body.raw:
        raise EvidenceIntegrityError(
            "Public viewport must retain canonical complete bytes"
        )
    result.require_observation(observed.record, observed.text)
    control.checkpoint()
    return result
