"""Engineering in-memory wire with real immutable test-only evidence storage."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
from typing import Any
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from evidence_control_fixtures import EvidenceFixtureStore
from test_site_task_wire import ready
from test_site_task_execution import request
from test_slurm_commands import guard


def put(store: EvidenceFixtureStore, value: Any) -> EvidenceRef:
    return store.put(
        value.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=value.schema_version,
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )


class Authority:
    def __init__(self, store: EvidenceFixtureStore) -> None:
        self.store, self.calls, self.deny = store, 0, False

    def verify_resume(
        self,
        config: SiteWorkerConfiguration,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        self.calls += 1
        value = SiteResumeIntent.model_validate_json(
            self.store.read(intent_ref, control)
        )
        assert value.request == request
        assert (
            value.configuration_sha256
            == hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        )
        if self.deny:
            raise PermissionError("resume denied")


def case(root: Path, monkeypatch: Any) -> Any:
    instance, service, channel, client, _ = ready()
    store = EvidenceFixtureStore(root)
    original = request()
    restore = original.model_copy(
        update={
            "action": "restore",
            "operation": original.operation.cleanup(
                "restore", now=datetime.now(timezone.utc), seconds=30
            ),
        }
    )
    result = SiteTaskResult(
        request_sha256=restore.digest, private_result='{"restored":true}'
    )
    ref = put(store, result)
    op = restore.operation.cleanup(
        "resume", now=datetime.now(timezone.utc), seconds=30
    ).model_copy(update={"recovery_ref": client.configuration.token.recovery_ref})
    req = SiteResumeRequest(
        restore_request=restore, restore_result_ref=ref, operation=op
    )

    def resume(
        req: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        control.checkpoint()
        instance.calls.append("resume")
        if instance.error:
            raise instance.error
        return SiteResumeResult(
            request_sha256=req.digest, private_result='{"healthy":true}'
        )

    monkeypatch.setattr(instance, "resume_frontend", resume, raising=False)
    authority = Authority(store)
    recorder = RecordedSiteResume(client, store, authority)
    return instance, service, channel, client, store, authority, recorder, req
