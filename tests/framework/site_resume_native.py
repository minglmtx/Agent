"""Resume in the original registered worker, with explicit engineering authority."""

from datetime import datetime, timezone
import hashlib
from typing import Any
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeIntent,
    SiteResumeResult,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.shopping_admin.frontend_recovery_contract import (
    AdminFrontendRecovered,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRestored,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRestored,
    OrderEtaResumed,
)
from site_resource_fixtures import Case
from test_slurm_commands import guard


def resume_original(
    case: Case,
    site: SiteHandle,
    original: SiteTaskRequest,
    result: SiteTaskResult,
    *,
    browser_closure_ref: EvidenceRef | None = None,
) -> dict[str, Any]:
    if case.spec.configuration.site_id == "map":
        if browser_closure_ref is None:
            raise ValueError("Map resume requires original browser closure")
        from map_resume_native import resume_original as map_resume

        return map_resume(case, site, original, result, browser_closure_ref)
    if case.spec.configuration.site_id == "reddit":
        if browser_closure_ref is None:
            raise ValueError("Reddit resume requires original browser closure")
        from reddit_resume_native import resume_original as reddit_resume

        return reddit_resume(case, site, original, result, browser_closure_ref)
    if case.spec.configuration.site_id == "gitlab":
        if browser_closure_ref is None:
            raise ValueError("GitLab resume requires original browser closure")
        from gitlab_resume_native import resume_original as gitlab_resume

        return gitlab_resume(case, site, original, result, browser_closure_ref)
    store = case.evidence
    result_ref = store.put(
        result.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=result.schema_version,
            visibility="private",
            producer="actual-site-engineering",
        ),
        control=guard(10),
    )
    shopping = case.spec.configuration.site_id == "shopping"
    seconds = 180 if shopping else 60
    operation = original.operation.cleanup(
        "native-shopping-resume" if shopping else "native-resume",
        now=datetime.now(timezone.utc),
        seconds=seconds,
    ).model_copy(update={"recovery_ref": case.spec.token.recovery_ref})
    request = SiteResumeRequest(
        restore_request=original, restore_result_ref=result_ref, operation=operation
    )
    restored = (
        OrderEtaRestored.model_validate_json(result.private_result)
        if shopping
        else ProductRestored.model_validate_json(result.private_result)
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
            read_operation = case.op.cleanup(
                "resume-resource-read", now=datetime.now(timezone.utc), seconds=15
            )
            assert case.journal.read(config.token, read_operation).state == "acquired"
            intent = SiteResumeIntent.model_validate_json(
                store.read(intent_ref, control=control)
            )
            assert intent.request == request
            assert (
                intent.configuration_sha256
                == hashlib.sha256(config.model_dump_json().encode()).hexdigest()
            )
            assert (
                store.read(req.restore_result_ref, control=control)
                == result.model_dump_json().encode()
            )
            if isinstance(restored, OrderEtaRestored):
                assert restored.request == original
                assert restored.snapshot.state.service.files == config.files
                assert browser_closure_ref is not None
            else:
                assert (
                    restored.frontend.service.layout.instance_id
                    == config.token.expected_resource_id
                )
                assert restored.frontend.backend.drained
            if browser_closure_ref is not None:
                closed = ClosureReceipt.model_validate_json(
                    store.read(browser_closure_ref, control=control)
                )
                assert (
                    closed.status == "closed"
                    and closed.token.owner == config.token.owner
                )
                assert (
                    closed.token.attempt_id == original.operation.attempt_id
                    and closed.token.resource_kind == "browser"
                )
            # Fresh exclusive engineering fixture with no browser allocation.
            # Does not qualify old site-close coverage for formal environment reset.

    recorder = RecordedSiteResume(site.resume, store, Authority())
    ref = recorder.resume(request, control=guard(seconds))
    recorded = SiteResumeResult.model_validate_json(store.read(ref, control=guard(10)))
    recovered = (
        OrderEtaResumed.model_validate_json(recorded.private_result)
        if shopping
        else AdminFrontendRecovered.model_validate_json(recorded.private_result)
    )
    assert recorded == recorder.result and recorded.request_sha256 == request.digest
    if isinstance(recovered, OrderEtaResumed):
        assert isinstance(restored, OrderEtaRestored)
        assert recovered.request == request and recovered.restored == restored
        assert recovered.protected == restored.snapshot.protected
    else:
        assert isinstance(restored, ProductRestored)
        assert recovered.stopped == restored.frontend
        assert (
            recovered.state_restored_sha256
            == hashlib.sha256(restored.state.model_dump_json().encode()).hexdigest()
        )
        assert recovered.frontend_ready
    assert recorder.intent_ref is not None
    return dict(
        request=request.model_dump(mode="json"),
        result_ref=ref.model_dump(mode="json"),
        intent_ref=recorder.intent_ref.model_dump(mode="json"),
        recovered=recovered.model_dump(mode="json"),
        same_worker=True,
        actor_authorized=False,
        complete_reset_receipt=False,
    )
