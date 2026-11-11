"""Validate and persist complete, unactivated release candidates.

Registry composition and complete frozen files must pass before manifest put.
Repeated stage calls validate again and store the same canonical bytes; they do
not recreate assets, execute tasks or switch current. A failed put/readback may
already have committed. Original exception type/chain is retained with a
release_candidate observation for explicit reconciliation of that exact object.
"""

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.registration import SupportedInterface
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.release_candidate import (
    CandidateCommitObservation,
    ReleaseCandidate,
    candidate_reference,
)
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.releases import ReleaseDocuments, ReleaseFiles
from lab_generate_skill.registry.resolve import TaskRegistry


class ReleaseCandidates:
    def __init__(self, documents: ReleaseDocuments, files: ReleaseFiles) -> None:
        self._documents, self._files = documents, files

    def stage(
        self,
        manifest: ReleaseManifest,
        registry_ref: EvidenceRef,
        supported: tuple[SupportedInterface, ...],
        control: OperationControl,
    ) -> ReleaseCandidate:
        manifest = ReleaseManifest.model_validate(manifest)
        registry_ref = EvidenceRef.model_validate(registry_ref)
        private_state_ref(registry_ref, "task-registry/1")
        if type(supported) is not tuple or not supported:
            raise ValueError("Explicit supported interfaces are required")
        supported = tuple(SupportedInterface.model_validate(x) for x in supported)
        if len(set(supported)) != len(supported):
            raise ValueError("Duplicate supported interface")
        control.checkpoint()
        registry = self._documents.registry(registry_ref, control)
        TaskRegistry(registry, registry_ref, manifest, supported)
        control.checkpoint()
        self._files.verify(manifest, control)
        control.checkpoint()
        candidate = ReleaseCandidate(candidate_reference(manifest), registry_ref)
        observation = CandidateCommitObservation(candidate, "put")
        try:
            actual = self._documents.put(manifest, control)
            if actual != candidate.manifest_ref:
                raise EvidenceIntegrityError("Candidate publication reference differs")
            observation = CandidateCommitObservation(candidate, "readback")
            control.checkpoint()
            loaded = self._documents.manifest(candidate.manifest_ref, control)
            if ReleaseManifest.model_validate(loaded) != manifest:
                raise EvidenceIntegrityError("Candidate readback differs from manifest")
            observation = CandidateCommitObservation(candidate, "confirmed")
            control.checkpoint()
            return candidate
        except BaseException as error:
            error.release_candidate = observation  # type: ignore[attr-defined]
            raise
