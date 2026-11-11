"""Bounded strict parsing of already-read release evidence, without I/O."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_RELEASE_BYTES = 32 * 1024 * 1024


def load_release(raw: bytes, reference: EvidenceRef) -> ReleaseManifest:
    reference = EvidenceRef.model_validate(reference)
    private_state_ref(reference, "release-manifest/1")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RELEASE_BYTES:
        raise EvidenceIntegrityError("Release evidence outside byte budget")
    if (
        reference.size_bytes != len(raw)
        or hashlib.sha256(raw).hexdigest() != reference.sha256
    ):
        raise EvidenceIntegrityError("Release evidence differs from frozen reference")
    try:
        json_object(raw)
        return ReleaseManifest.model_validate_json(raw)
    except ValueError as error:
        raise EvidenceIntegrityError("Invalid release manifest") from error
