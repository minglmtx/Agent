"""Original complete final state after browser closure, before restore/resume."""

import hashlib
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import MapCapturePair
from lab_generate_skill.ports.map_terminal import OriginalMapTerminal
from .tasks.state_codec import MapTaskStateCodec
from .tasks.overlay_environment import OverlayEnvironmentChecks, MapEnvironmentFacts
from .tasks.state_admission import snapshot_reference


def complete_final_guard(
    pair: MapCapturePair,
    closure: ClosureReceipt,
    terminal: OriginalMapTerminal,
    environment: MapEnvironmentFacts,
    reads: OverlayEnvironmentChecks,
    snapshot_ref: EvidenceRef,
    control: OperationControl,
) -> None:
    intent = reads.read(
        pair.intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
    )
    result = reads.read(pair.result_ref, "site-task-result/1", SiteTaskResult, control)
    request = intent.request
    request.check_site(environment.site.configuration)
    inspection = request.inspection
    snapshot = environment.snapshot
    codec = MapTaskStateCodec(snapshot.request.task)
    snapshot_reference(
        inspection,
        snapshot.request,
        snapshot.model_dump_json().encode(),
        snapshot_ref,
        schema_version=codec.snapshot_schema,
    )
    if (
        closure.token != terminal.initial.browser.token
        or closure.status != "closed"
        or inspection.operation.parent_operation_id != closure.operation_id
        or (request.collector_id, request.collector_version) != (codec.collector, "1")
        or request.selection_ref is not None
        or intent.configuration_sha256
        != hashlib.sha256(
            environment.site.configuration.model_dump_json().encode()
        ).hexdigest()
        or result.request_sha256 != request.digest
        or inspection.operation.operation_id
        in (
            snapshot.request.operation.operation_id,
            terminal.initial.returned.operation.operation_id,
            terminal.intent.request.operation.operation_id,
        )
    ):
        raise EvidenceIntegrityError(
            "Map final guard requires original closed browser and distinct original inspection"
        )
    observed = codec.observed_type.model_validate_json(result.private_result)
    if (
        observed.model_dump_json() != result.private_result
        or observed.request != inspection
        or observed.snapshot != snapshot
    ):
        raise EvidenceIntegrityError(
            "Map final guard changed original request/snapshot"
        )
    before = reads.native(snapshot.native, snapshot.request, control)
    after = reads.native(observed.native, inspection, control)
    if before.sha256 != after.sha256:
        raise EvidenceIntegrityError("Complete original Map persistent state changed")
