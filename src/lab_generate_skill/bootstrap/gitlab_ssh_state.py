"""Selected complete native wire decoder, injected into site semantics."""

from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import SshKeyNativeState


def load_ssh_key_state(raw: bytes, spec: SshKeySpec) -> SshKeyNativeState:
    spec = SshKeySpec.model_validate(spec)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_OBJECT_BYTES:
        raise ValueError("Complete private native state exceeds its CAS byte budget")
    json_object(raw)
    value = SshKeyNativeState.model_validate_json(raw)
    if value.task != spec.task:
        raise EvidenceIntegrityError("Private native SSH state changed original task")
    return value
