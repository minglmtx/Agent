"""Strict release/registry CAS documents, without filesystem or plugin policy.

Worker-local synchronous adapter. It never creates assets, chooses a current
release, activates plugins or retries. Caller owns external I/O supervision.
"""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.registration import RegistryManifest
from lab_generate_skill.domain.release_candidate import (
    RELEASE_METADATA,
    candidate_reference,
)
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .manifest import MAX_RELEASE_BYTES, load_release
from .registry_manifest import load_registry


class EvidenceReleaseDocuments:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def registry(
        self, reference: EvidenceRef, control: OperationControl
    ) -> RegistryManifest:
        reference = EvidenceRef.model_validate(reference)
        private_state_ref(reference, "task-registry/1")
        if not 1 <= reference.size_bytes <= 8 * 1024 * 1024:
            raise EvidenceIntegrityError("Registry reference exceeds byte budget")
        control.checkpoint()
        result = load_registry(self._store.read(reference, control=control), reference)
        control.checkpoint()
        return result

    def manifest(
        self, reference: EvidenceRef, control: OperationControl
    ) -> ReleaseManifest:
        reference = EvidenceRef.model_validate(reference)
        private_state_ref(reference, "release-manifest/1")
        if not 1 <= reference.size_bytes <= MAX_RELEASE_BYTES:
            raise EvidenceIntegrityError("Release reference exceeds byte budget")
        control.checkpoint()
        result = load_release(self._store.read(reference, control=control), reference)
        control.checkpoint()
        return result

    def put(self, manifest: ReleaseManifest, control: OperationControl) -> EvidenceRef:
        manifest = ReleaseManifest.model_validate(manifest)
        raw = manifest.model_dump_json().encode()
        if len(raw) > MAX_RELEASE_BYTES:
            raise EvidenceIntegrityError("Candidate manifest exceeds byte budget")
        control.checkpoint()
        reference = self._store.put(raw, RELEASE_METADATA, control=control)
        if reference != candidate_reference(manifest):
            raise EvidenceIntegrityError("Candidate store returned another reference")
        control.checkpoint()
        return reference
