"""Derive an immutable CAS identity without reading or writing the filesystem.

Used before dispatch and by the storage primitive. A known reference identifies
expected bytes, not proof of publication, durability, provenance or permission.
"""

import hashlib
from .evidence import EvidenceMetadata, EvidenceRef


def evidence_reference(data: bytes, metadata: EvidenceMetadata) -> EvidenceRef:
    if type(data) is not bytes:
        raise TypeError("Evidence payload must be immutable bytes")
    if not isinstance(metadata, EvidenceMetadata):
        raise TypeError("Evidence metadata must be EvidenceMetadata")
    metadata = EvidenceMetadata.model_validate(metadata)
    digest = hashlib.sha256(data).hexdigest()
    return EvidenceRef(
        uri=f"cas://sha256/{digest}",
        sha256=digest,
        size_bytes=len(data),
        media_type=metadata.media_type,
        content_schema=metadata.content_schema,
        visibility=metadata.visibility,
        producer=metadata.producer,
    )
