"""Decode complete captured group bytes using the common strict wire reader."""

from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_state import GroupNativeState


def load_group_state(raw: bytes, spec: GroupSpec) -> GroupNativeState:
    spec = GroupSpec.model_validate(spec)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_OBJECT_BYTES:
        raise ValueError("Complete native group state exceeds its CAS byte budget")
    json_object(raw)
    value = GroupNativeState.model_validate_json(raw)
    if value.task != spec.task or (value.settings is not None) != (
        spec.requirements.settings is not None
    ):
        raise EvidenceIntegrityError(
            "Native group task or declared settings coverage differs"
        )
    return value
