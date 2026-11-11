"""Recompute a complete original guard fact; a handle digest is insufficient."""

from dataclasses import dataclass
import json
from lab_generate_skill.domain.map_state import MapPersistentState
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .state_rules import object_json, database_state, fingerprint


@dataclass(frozen=True)
class CompleteMapState:
    database: bytes
    persistent: MapPersistentState
    sha256: str


def complete_state(
    raw: bytes, descriptor: MapStateArtifact, request: SiteTaskRequest
) -> CompleteMapState:
    if type(raw) is not bytes or not raw or len(raw) != descriptor.file.size_bytes:
        raise EvidenceIntegrityError("Complete original Map state bytes required")
    value = object_json(raw)
    if set(value) != {
        "schema_version",
        "request_sha256",
        "database",
        "persistent",
        "sha256",
    } or (value["schema_version"], value["request_sha256"]) != (
        "map-complete-guard/1",
        request.digest,
    ):
        raise EvidenceIntegrityError("Original Map guard record fields/request changed")
    if type(value["database"]) is not str or type(value["persistent"]) is not dict:
        raise EvidenceIntegrityError(
            "Complete original Map database/persistent fields required"
        )
    if json.dumps(value, sort_keys=True).encode() != raw:
        raise EvidenceIntegrityError("Noncanonical original Map guard record")
    database = value["database"].encode("utf-8")
    persistent = MapPersistentState.model_validate_json(json.dumps(value["persistent"]))
    digest = fingerprint(persistent, database)
    if (
        database_state(database)["changed"]
        or digest != value["sha256"]
        or digest != descriptor.state_sha256
    ):
        raise EvidenceIntegrityError(
            "Original complete Map state changed or fingerprint is false"
        )
    return CompleteMapState(database, persistent, digest)
