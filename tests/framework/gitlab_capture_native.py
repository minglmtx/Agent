"""Original registered selected GitLab inspect/capture with persisted exact request admission."""

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
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRecoverySnapshot,
    SshKeyObserved,
)
from site_resource_fixtures import Case
from test_slurm_commands import guard
from gitlab_source_selection import check_gitlab_task
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRecoverySnapshot,
    GroupObserved,
)


def capture_original(
    case: Case, site: SiteHandle, prepared: SiteTaskRequest, label: str
) -> dict[str, Any]:
    prepared = SiteTaskRequest.model_validate(prepared)
    prepared.check_site(case.spec.configuration)
    assert prepared.action == "prepare" and prepared.snapshot_ref is not None
    group = check_gitlab_task(case.spec.configuration, prepared.task)
    snapshot_type = GroupRecoverySnapshot if group else SshKeyRecoverySnapshot
    snapshot = snapshot_type.model_validate_json(
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
                    "operation_id": ("native-group-" if group else "native-ssh-")
                    + label,
                    "deadline": datetime.now(timezone.utc) + timedelta(seconds=180),
                }
            ),
        }
    )
    request = SiteCaptureRequest(
        inspection=inspection,
        collector_id="gitlab-group-creation" if group else "gitlab-profile-ssh-key",
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
                "gitlab-capture-ledger-" + label,
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
    observed_type = GroupObserved if group else SshKeyObserved
    observed = observed_type.model_validate_json(result.private_result)
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
