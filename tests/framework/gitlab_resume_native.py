"""Confirm original restored GitLab generation, after original browser closure."""

from datetime import datetime, timezone
import hashlib
from typing import Any
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRestored,
    SshKeyResumed,
)
from site_resource_fixtures import Case
from test_slurm_commands import guard
from gitlab_source_selection import check_gitlab_task
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRestored,
    GroupResumed,
)


def resume_original(
    case: Case,
    site: SiteHandle,
    original: SiteTaskRequest,
    result: SiteTaskResult,
    browser_closure_ref: EvidenceRef,
) -> dict[str, Any]:
    original = SiteTaskRequest.model_validate(original)
    result = SiteTaskResult.model_validate(result)
    original.check_site(case.spec.configuration)
    group = check_gitlab_task(case.spec.configuration, original.task)
    restored_type = GroupRestored if group else SshKeyRestored
    restored = restored_type.model_validate_json(result.private_result)
    if (
        result.request_sha256 != original.digest
        or restored.request != original
        or restored.snapshot.state.service.files != case.spec.configuration.files
    ):
        raise ValueError("GitLab resume changed original restore request/result/site")
    store = case.evidence
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
        "native-gitlab-resume", now=datetime.now(timezone.utc), seconds=180
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
            assert config == case.spec.configuration and req == request
            assert (
                case.journal.read(
                    config.token,
                    case.op.cleanup(
                        "gitlab-resume-resource-read",
                        now=datetime.now(timezone.utc),
                        seconds=15,
                    ),
                ).state
                == "acquired"
            )
            intent = SiteResumeIntent.model_validate_json(
                store.read(intent_ref, control=control)
            )
            assert (
                intent.request == req
                and intent.configuration_sha256
                == hashlib.sha256(config.model_dump_json().encode()).hexdigest()
            )
            assert (
                store.read(req.restore_result_ref, control=control)
                == result.model_dump_json().encode()
            )
            assert (
                restored.request == original
                and restored.snapshot.state.service.files == config.files
            )
            closed = ClosureReceipt.model_validate_json(
                store.read(browser_closure_ref, control=control)
            )
            assert (
                closed.status == "closed" and closed.token.owner == config.token.owner
            )
            assert (
                closed.token.resource_kind == "browser"
                and closed.token.attempt_id == original.operation.attempt_id
            )
            control.checkpoint()

    recorder = RecordedSiteResume(site.resume, store, Authority())
    result_ref = recorder.resume(request, control=guard(180))
    assert (
        recorder.result is not None
        and recorder.result.request_sha256 == request.digest
        and recorder.intent_ref is not None
    )
    resumed_type = GroupResumed if group else SshKeyResumed
    recovered = resumed_type.model_validate_json(recorder.result.private_result)
    assert recovered.request == request and recovered.restored == restored
    return dict(
        request=request.model_dump(mode="json"),
        result_ref=result_ref.model_dump(mode="json"),
        intent_ref=recorder.intent_ref.model_dump(mode="json"),
        recovered=recovered.model_dump(mode="json"),
        same_worker=True,
        actor_authorized=False,
        complete_reset_receipt=False,
    )
