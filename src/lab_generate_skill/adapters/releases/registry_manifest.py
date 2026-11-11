"""Parse canonical registry evidence without importing implementation modules."""

import hashlib
from lab_generate_skill.domain.registration import RegistryManifest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object


def load_registry(raw: bytes, reference: EvidenceRef) -> RegistryManifest:
    reference = EvidenceRef.model_validate(reference)
    private_state_ref(reference, "task-registry/1")
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= 8 * 1024 * 1024
        or reference.size_bytes != len(raw)
        or reference.sha256 != hashlib.sha256(raw).hexdigest()
    ):
        raise EvidenceIntegrityError("Registry evidence differs from bounded reference")
    try:
        json_object(raw)
        manifest = RegistryManifest.model_validate_json(raw)
        if manifest.model_dump_json().encode() != raw:
            raise ValueError("Registry must use its canonical serialization")
        return manifest
    except ValueError as error:
        raise EvidenceIntegrityError("Invalid original registry document") from error
