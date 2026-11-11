"""Map passive captures keep the original source and durable intent authority."""

from datetime import datetime, timezone, timedelta
import hashlib
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.sites.map.evidence_schema import MapCapturePair
from map_qualified_source_native import MapQualifiedSource
from map_site_engineering_authority import MapEngineeringAuthority


def inspection(
    source: MapQualifiedSource, name: str, *, parent: str | None = None
) -> SiteTaskRequest:
    prepared = source.native.request
    if prepared is None:
        raise ValueError("Original Map prepare request required")
    return SiteTaskRequest.model_validate(
        prepared.model_copy(
            update={
                "action": "inspect",
                "operation": prepared.operation.model_copy(
                    update={
                        "operation_id": name,
                        "parent_operation_id": parent,
                        "deadline": datetime.now(timezone.utc) + timedelta(seconds=600),
                    }
                ),
            }
        )
    )


class MapCaptureAuthority:
    def __init__(
        self,
        source: MapQualifiedSource,
        *,
        task_authority: MapEngineeringAuthority | None = None,
    ) -> None:
        self.source = source
        self.task_authority = task_authority

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        source = self.source
        authority = (
            source.c.authority if self.task_authority is None else self.task_authority
        )
        if not isinstance(authority, MapEngineeringAuthority):
            raise OwnershipConflict("Original Map source/resource authority required")
        intent = SiteCaptureIntent.model_validate_json(
            source.c.evidence.read(intent_ref, control=control)
        )
        if (
            configuration != source.c.spec.configuration
            or intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
            or source.native.request is None
            or request.inspection.binding_ref != source.native.binding_ref
            or request.inspection.snapshot_ref != source.native.request.snapshot_ref
        ):
            raise OwnershipConflict("Original Map source/capture intent changed")
        authority.verify_task(configuration, request.inspection, control)


def capture(
    source: MapQualifiedSource,
    request: SiteCaptureRequest,
    authority: SiteCaptureAuthority,
) -> MapCapturePair:
    owner = source.c.authority
    if not isinstance(owner, MapEngineeringAuthority):
        raise OwnershipConflict("Original Map source/resource authority required")
    # Intent publication is not a dispatch; the existing worker still consumes
    # the original operation and request once, including unknown outcomes.
    operation_id = request.operation.operation_id
    if operation_id in owner.task_intents:
        raise OwnershipConflict("Original Map capture was already declared")
    owner.task_intents[operation_id] = source.native.put(request.inspection)
    recorder = RecordedSiteCapture(source.site.capture, source.c.evidence, authority)
    result = recorder.capture(
        request, control=source.c.controls.bind(request.operation)
    )
    assert recorder.intent_ref is not None
    return MapCapturePair(intent_ref=recorder.intent_ref, result_ref=result)
