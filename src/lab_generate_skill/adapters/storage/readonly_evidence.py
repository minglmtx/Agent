"""Worker-internal readonly CAS; exact proposed summaries have no disk effects."""

from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.closed_source_read import ClosedSourcePublicationInput
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .filesystem import FileEvidenceStore


class ReadOnlyEvidence:
    def __init__(
        self,
        root: Path,
        *,
        max_object_bytes: int,
        proposed: ClosedSourcePublicationInput | None = None,
        reuse_within_proof: bool = False,
    ) -> None:
        if type(reuse_within_proof) is not bool:
            raise TypeError("Proof-local immutable body reuse requires explicit bool")
        self.reuse_within_proof = reuse_within_proof
        self._bodies: dict[str, bytes] = {}
        self._body_bytes = 0
        self._body_limit = max_object_bytes
        self.body_read_count = 0
        self.store = FileEvidenceStore(
            root, max_object_bytes=max_object_bytes, initialize=False
        )
        self.read_count = 0
        self.unique_objects: set[str] = set()
        self.proposed: dict[str, tuple[EvidenceRef, bytes, EvidenceMetadata]] = {}
        if proposed is None:
            return
        proposed = ClosedSourcePublicationInput.model_validate(proposed)
        # Four explicit proposed values without write capability. Other bodies
        # are physically read from original CAS on first use in this proof.
        for value, visibility, producer in (
            (proposed.public, "public", "source-qualification-context-v1"),
            (proposed.baseline, "private", "state-records-v1"),
            (proposed.reset, "private", "state-records-v1"),
            (proposed.context, "private", "context-records-v1"),
        ):
            raw = value.model_dump_json().encode()
            metadata = EvidenceMetadata.model_validate(
                {
                    "media_type": "application/json",
                    "content_schema": value.schema_version,
                    "visibility": visibility,
                    "producer": producer,
                }
            )
            reference = evidence_reference(raw, metadata)
            self.proposed[reference.sha256] = reference, raw, metadata
        context = proposed.context
        if any(
            ref.sha256 not in self.proposed or self.proposed[ref.sha256][0] != ref
            for ref in (
                context.baseline_ref,
                context.reset_ref,
                context.public_context_ref,
            )
        ):
            raise OwnershipConflict(
                "Proposed summary references differ from their exact bytes"
            )

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        if not isinstance(reference, EvidenceRef):
            raise TypeError("Original exact EvidenceRef required")
        reference = EvidenceRef.model_validate(reference)
        control.checkpoint()
        # The primitive's original location check also applies on a body hit.
        # Metadata remains on each complete ref; it never keys permissions.
        if reference.uri != f"cas://sha256/{reference.sha256}":
            raise EvidenceIntegrityError(
                "Reference does not identify this store's CAS object"
            )
        item = self.proposed.get(reference.sha256)
        if item is not None and item[0] != reference:
            raise OwnershipConflict("Proposed source metadata changed")
        if item is not None:
            value = item[1]
        elif self.reuse_within_proof and reference.sha256 in self._bodies:
            value = self._bodies[reference.sha256]
        else:
            value = self.store.read(reference)
            self.body_read_count += 1
            if (
                self.reuse_within_proof
                and self._body_bytes + len(value) <= self._body_limit
            ):
                self._bodies[reference.sha256] = value
                self._body_bytes += len(value)
        # This is immutable-body reuse, never reference/permission reuse.
        # The fixed caller still performs all original semantic checks and its
        # parent/session/owner admission before and after each fresh proof.
        require_complete_bytes(reference, value)
        self.read_count += 1
        self.unique_objects.add(reference.sha256)
        control.checkpoint()
        return value

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        control.checkpoint()
        reference = evidence_reference(data, metadata)
        if self.proposed.get(reference.sha256) != (reference, data, metadata):
            raise PermissionError("Closed source proof has no publication capability")
        # Original record publishers validate their exact proposed value here;
        # this acknowledgement performs no filesystem write and grants nothing.
        return reference
