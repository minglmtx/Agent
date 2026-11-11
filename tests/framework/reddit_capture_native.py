"""Original registered image inspect/capture with persisted exact request admission."""

from datetime import datetime, timezone, timedelta
import hashlib
from typing import Any
from lab_generate_skill.domain.site_capture import SiteCaptureIntent, SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.reddit.tasks.image_recovery import (
    ImageRecoverySnapshot,
    ImageObserved,
)
from site_resource_fixtures import Case
from test_slurm_commands import guard


def capture_original(
    case: Case, site: SiteHandle, prepared: SiteTaskRequest, label: str
) -> dict[str, Any]:
    assert prepared.action == "prepare" and prepared.snapshot_ref is not None
    snapshot = ImageRecoverySnapshot.model_validate_json(
        case.evidence.read(prepared.snapshot_ref, control=guard(10))
    )
    assert (
        snapshot.request.task == prepared.task
        and snapshot.request.binding_ref == prepared.binding_ref
    )
    assert snapshot.state.service.files == case.spec.configuration.files
    inspection = prepared.model_copy(
        update={
            "action": "inspect",
            "operation": prepared.operation.model_copy(
                update={
                    "operation_id": "native-image-" + label,
                    "deadline": datetime.now(timezone.utc) + timedelta(seconds=180),
                }
            ),
        }
    )
    request = SiteCaptureRequest(
        inspection=inspection,
        collector_id="reddit-native-image",
        collector_version="1",
    )

    class Authority:
        def verify_capture(
            self,
            config: SiteWorkerConfiguration,
            req: SiteCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            assert config == case.spec.configuration and req == request
            intent = SiteCaptureIntent.model_validate_json(
                case.evidence.read(intent_ref, control=control)
            )
            assert (
                intent.request == req
                and intent.configuration_sha256
                == hashlib.sha256(config.model_dump_json().encode()).hexdigest()
            )
            read = case.op.cleanup(
                "image-capture-ledger-" + label,
                now=datetime.now(timezone.utc),
                seconds=15,
            )
            assert case.journal.read(config.token, read).state == "acquired"
            control.checkpoint()

    recorder = RecordedSiteCapture(site.capture, case.evidence, Authority())
    ref = recorder.capture(request, control=guard(180))
    result = SiteTaskResult.model_validate_json(
        case.evidence.read(ref, control=guard(10))
    )
    observed = ImageObserved.model_validate_json(result.private_result)
    assert (
        result == recorder.result
        and result.request_sha256 == request.digest
        and observed.request == inspection
    )
    assert observed.snapshot == snapshot and recorder.intent_ref is not None
    return dict(
        request=request.model_dump(mode="json"),
        intent_ref=recorder.intent_ref.model_dump(mode="json"),
        result_ref=ref.model_dump(mode="json"),
        catalog=observed.model_dump(mode="json"),
        engineering_only=True,
    )
