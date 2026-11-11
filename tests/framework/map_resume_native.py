"""Original registered Map restore/resume with closed-browser and exact intent checks."""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any
import hashlib
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_recovery import (
    OverlayRestored,
    OverlayResumed,
)
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from site_resource_fixtures import Case
from test_slurm_commands import guard


def resume_original(
    case: Case,
    site: SiteHandle,
    original: SiteTaskRequest,
    result: SiteTaskResult,
    browser_closure_ref: EvidenceRef,
) -> dict[str, Any]:
    store = case.evidence
    codec = MapTaskStateCodec(original.task)
    restored = codec.restored_type.model_validate_json(result.private_result)
    if (
        restored.request != original
        or restored.snapshot.native.plan.token != case.spec.token
    ):
        raise OwnershipConflict("Original Map restore/allocation changed")
    ref = store.put(
        result.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=result.schema_version,
            visibility="private",
            producer="actual-site-engineering",
        ),
        control=guard(10),
    )
    operation = original.operation.cleanup(
        "native-map-resume", now=datetime.now(timezone.utc), seconds=600
    ).model_copy(update={"recovery_ref": case.spec.token.recovery_ref})
    request = SiteResumeRequest(
        restore_request=original, restore_result_ref=ref, operation=operation
    )

    class Authority:
        def verify_resume(
            self,
            config: SiteWorkerConfiguration,
            req: SiteResumeRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            control.checkpoint()
            intent = SiteResumeIntent.model_validate_json(
                store.read(intent_ref, control=control)
            )
            closed = ClosureReceipt.model_validate_json(
                store.read(browser_closure_ref, control=control)
            )
            if (
                config != case.spec.configuration
                or req != request
                or intent.request != req
                or intent.configuration_sha256
                != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
                or store.read(req.restore_result_ref, control=control)
                != result.model_dump_json().encode()
                or closed.status != "closed"
                or closed.token.owner != config.token.owner
                or closed.token.resource_kind != "browser"
                or closed.token.attempt_id != original.operation.attempt_id
            ):
                raise OwnershipConflict(
                    "Original Map restore/intent/browser closure changed"
                )
            read = case.op.cleanup(
                "map-resume-read-" + uuid4().hex,
                now=datetime.now(timezone.utc),
                seconds=15,
            )
            if case.journal.read(config.token, read).state != "acquired":
                raise OwnershipConflict("Original Map instance is not acquired")
            control.checkpoint()

    recorder = RecordedSiteResume(site.resume, store, Authority())
    result_ref = recorder.resume(request, control=case.controls.bind(operation))
    assert recorder.result is not None and recorder.intent_ref is not None
    recovered = codec.resumed_type.model_validate_json(recorder.result.private_result)
    if recovered.request != request or recovered.restored != restored:
        raise OwnershipConflict("Map resume returned another recovery")
    return dict(
        request=request.model_dump(mode="json"),
        result_ref=result_ref.model_dump(mode="json"),
        intent_ref=recorder.intent_ref.model_dump(mode="json"),
        recovered=recovered.model_dump(mode="json"),
        same_worker=True,
        actor_authorized=False,
        complete_reset_receipt=False,
    )
