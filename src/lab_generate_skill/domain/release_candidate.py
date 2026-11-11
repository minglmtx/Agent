"""Canonical identity and diagnostic facts for an unactivated release candidate.

A reference is not permission, proof of deployment, or a unique release-ID
reservation. Activation must bind the exact digest and separately check loading,
admission, acceptance and current revision. No caller can infer these from CAS.
"""

from dataclasses import dataclass
from typing import Literal
from .evidence import EvidenceMetadata, EvidenceRef
from .evidence_identity import evidence_reference
from .release import ReleaseManifest

RELEASE_METADATA = EvidenceMetadata(
    media_type="application/json",
    content_schema="release-manifest/1",
    visibility="private",
    producer="release-candidates-v1",
)


def candidate_reference(manifest: ReleaseManifest) -> EvidenceRef:
    manifest = ReleaseManifest.model_validate(manifest)
    return evidence_reference(manifest.model_dump_json().encode(), RELEASE_METADATA)


@dataclass(frozen=True)
class ReleaseCandidate:
    """Returned only after registry/files checks and exact CAS readback."""

    manifest_ref: EvidenceRef
    registry_ref: EvidenceRef


@dataclass(frozen=True)
class CandidateCommitObservation:
    """Expected bytes, not a claim of commitment; attached to original failures."""

    candidate: ReleaseCandidate
    phase: Literal["put", "readback", "confirmed"]
