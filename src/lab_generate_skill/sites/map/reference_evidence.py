"""Read original capture bindings and complete DB bytes; never query or relabel a comparison."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_database_artifact import MapDatabaseArtifact
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_published_files import MapPublishedFiles
from .terminal_evidence import TerminalMapEvidence
from .terminal_files import private_record
from .reference_selection import read_reference_selection, verify_reference_selection
from .tasks.state_admission import snapshot_reference
from .tasks.overlay_recovery import OverlaySnapshot
from .native_database_program import reference_program
from .native_compare import compare_database
from .state_rules import object_json


def reference_artifact(
    store: EvidenceReader,
    configuration: SiteWorkerConfiguration,
    intent_ref: EvidenceRef,
    result_ref: EvidenceRef,
    control: OperationControl,
) -> MapDatabaseArtifact:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    intent = private_record(
        store, intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
    )
    result = private_record(
        store, result_ref, "site-task-result/1", SiteTaskResult, control
    )
    request = intent.request
    request.check_site(configuration)
    if (
        intent.configuration_sha256
        != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
    ):
        raise OwnershipConflict(
            "Reference capture changed original configuration/request"
        )
    artifact = MapDatabaseArtifact.model_validate_json(result.private_result)
    if (
        artifact.model_dump_json() != result.private_result
        or artifact.request != request
        or request.selection_ref is None
        or request.inspection.snapshot_ref is None
    ):
        raise OwnershipConflict("Original selected capture and snapshot required")
    selected = read_reference_selection(
        store, request.selection_ref, request.inspection, control
    )
    snapshot = private_record(
        store,
        request.inspection.snapshot_ref,
        "map-overlay-snapshot/1",
        OverlaySnapshot,
        control,
    )
    snapshot_reference(
        request.inspection,
        snapshot.request,
        snapshot.model_dump_json().encode(),
        None,
        schema_version="map-overlay-snapshot/1",
    )
    if (
        artifact.selected != selected
        or artifact.before_sha256 != snapshot.native.state_sha256
        or artifact.plan.scope != snapshot.native.plan.scope
        or artifact.plan.token != snapshot.native.plan.token
    ):
        raise OwnershipConflict(
            "Native reference changed selected response or original full baseline"
        )
    return artifact


@dataclass(frozen=True)
class MapReferenceRead:
    artifact: MapDatabaseArtifact
    payload: bytes
    database: bytes
    comparison: dict[str, Any]


def read_reference_files(
    artifact: MapDatabaseArtifact,
    terminal: TerminalMapEvidence,
    store: EvidenceReader,
    configuration: SiteWorkerConfiguration,
    started: SiteInstanceStarted,
    files: MapPublishedFiles,
    control: OperationControl,
) -> MapReferenceRead:
    artifact = MapDatabaseArtifact.model_validate(artifact)
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    started = SiteInstanceStarted.model_validate(started)
    selected = artifact.selected
    verify_reference_selection(
        selected, terminal, artifact.request.inspection, store, control
    )
    manifest = files.manifest(artifact.handle, control)
    label = f"layer-final-{selected.request_index}"
    names = (
        label + "-intent.json",
        label + "-reference.rb",
        artifact.output.path,
        label + "-complete.json",
    )
    members = {f.path: f for f in manifest.artifact.files}
    if (
        manifest.plan != artifact.plan
        or set(members) != set(names)
        or members.get(artifact.output.path) != artifact.output
        or any(f.executable for f in members.values())
    ):
        raise EvidenceIntegrityError(
            "Original complete native reference manifest differs"
        )

    def read(name: str) -> bytes:
        raw = files.read(artifact.handle, name, control)
        pin = members[name]
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (pin.size_bytes, pin.sha256):
            raise EvidenceIntegrityError(
                "Complete reference bytes differ from manifest"
            )
        return raw

    intent = object_json(read(names[0]))
    if set(intent) != {"export", "artifact_plan_sha256", "before_sha256"}:
        raise EvidenceIntegrityError("Complete original query intent required")
    export = MapDatabaseExport.model_validate_json(json.dumps(intent["export"]))
    inputs = configuration.map_inputs
    if (
        inputs is None
        or export.spec.inputs != inputs.runtime
        or started.files != configuration.files
        or export.spec.endpoint != started.endpoint
        or tuple(export.spec.ports.model_dump().values()) != started.ports
        or export.max_output_bytes != artifact.plan.max_file_bytes
        or export.label != label
        or intent["artifact_plan_sha256"] != artifact.plan.digest
        or intent["before_sha256"] != artifact.before_sha256
    ):
        raise OwnershipConflict(
            "Native query changed original instance, bounds or baseline"
        )
    program = read(names[1])
    if program != reference_program(
        selected.bounds, label, artifact.plan.max_file_bytes
    ) or (len(program), hashlib.sha256(program).hexdigest()) != (
        export.program.size_bytes,
        export.program.sha256,
    ):
        raise EvidenceIntegrityError("Original complete query program differs")
    complete = json.dumps(
        dict(
            output=artifact.output.model_dump(mode="json"),
            artifact_plan_sha256=artifact.plan.digest,
            before_sha256=artifact.before_sha256,
            after_sha256=artifact.after_sha256,
        ),
        sort_keys=True,
    ).encode()
    if read(names[3]) != complete:
        raise EvidenceIntegrityError("Original query completion differs")
    database = read(artifact.output.path)
    payload = terminal.files.pinned(selected.payload, control)
    # The pure comparison deliberately retains provenance_verified=False and its
    # native-claim flags. Provenance resides in the verified original bindings.
    comparison = compare_database(
        payload,
        selected.bounds,
        object_json(database),
        response_kind=selected.response_kind,
    )
    control.checkpoint()
    return MapReferenceRead(artifact, payload, database, comparison)
