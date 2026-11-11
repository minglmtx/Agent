"""Strict complete capture decoder; never dispatches SQL or upgrades old input."""

from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_capture import (
    GroupCapturePayload,
    GroupCapturedFacts,
)
from .gitlab_group_state import load_group_state


def load_group_capture(raw: bytes, spec: GroupSpec) -> GroupCapturedFacts:
    spec = GroupSpec.model_validate(spec)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_OBJECT_BYTES:
        raise EvidenceIntegrityError("Complete Group capture exceeds private CAS bound")
    json_object(raw)
    payload = GroupCapturePayload.model_validate_json(raw)
    if payload.model_dump_json().encode() != raw or payload.task != spec.task:
        raise EvidenceIntegrityError("Group capture lost original canonical task")
    groups, projects = payload.original_replies()
    if json_object(groups).get("schema_version") != "gitlab-group-state/1":
        raise EvidenceIntegrityError("Original Group native reply schema required")
    state = load_group_state(groups, spec)
    return GroupCapturedFacts(state, groups, projects)
