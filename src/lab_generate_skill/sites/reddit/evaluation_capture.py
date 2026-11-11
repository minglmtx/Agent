"""Readonly native/page capture joins against original frozen resource declarations."""

import hashlib
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import ImageSiteCapture, ImagePageCapture, RedditPageHealth
from .state_reads import RedditStateReads
from .tasks.image_spec import NativeImageSpec
from .tasks.image_recovery import ImageObserved, ImageRecoverySnapshot
from .tasks.image_admission import task_input
from .native_schema import NativeCapture


def native_capture(
    reads: RedditStateReads,
    pair: ImageSiteCapture,
    contract: EvaluationContract,
    spec: NativeImageSpec,
    site: SiteResourceSpec,
    snapshot: ImageRecoverySnapshot,
    trace: InteractionTrace,
    snapshot_ref_sha: str,
    control: OperationControl,
) -> tuple[SiteCaptureIntent, NativeCapture]:
    intent = reads.read(
        pair.intent_ref, "site-capture-intent/2", SiteCaptureIntent, control
    )
    result = reads.read(pair.result_ref, "site-task-result/1", SiteTaskResult, control)
    req, task = intent.request, intent.request.inspection
    task.check_site(site.configuration)
    if (
        (req.collector_id, req.collector_version) != ("reddit-native-image", "1")
        or result.request_sha256 != req.digest
        or task.binding_ref != contract.task_contract_ref
        or task.task != contract.identity
        or task_input(task) != spec
        or (task.operation.run_id, task.operation.owner_id, task.operation.attempt_id)
        != (
            trace.scope.owner.run_id,
            trace.scope.owner.owner_id,
            trace.scope.attempt_id,
        )
        or intent.configuration_sha256
        != hashlib.sha256(site.configuration.model_dump_json().encode()).hexdigest()
        or task.snapshot_ref is None
        or task.snapshot_ref.sha256 != snapshot_ref_sha
    ):
        raise EvidenceIntegrityError("Reddit capture changed original task/site/scope")
    observed = ImageObserved.model_validate_json(result.private_result)
    if (
        observed.model_dump_json() != result.private_result
        or observed.request != task
        or observed.snapshot != snapshot
    ):
        raise EvidenceIntegrityError("Reddit capture lost original complete snapshot")
    snapshot.check_request(task)
    if observed.native.context != snapshot.native_before.context:
        raise EvidenceIntegrityError("Reddit capture changed original native worker")
    return intent, reads.capture(observed.native, task, control)


def page_capture(
    reads: RedditStateReads,
    pair: ImagePageCapture,
    browser: BrowserResourceSpec,
    trace: InteractionTrace,
    observed: Observation,
    control: OperationControl,
) -> RedditPageHealth:
    intent = reads.read(
        pair.intent_ref, "browser-capture-intent/1", BrowserCaptureIntent, control
    )
    result = reads.read(
        pair.result_ref, "browser-capture-result/1", BrowserCaptureResult, control
    )
    req = intent.request
    browser.check_operation(req.operation, "execute")
    if (
        req.scope != trace.scope
        or req.observation_sha256 != trace.final_observation_ref.sha256
        or (req.collector_id, req.collector_version) != ("reddit-page-health", "1")
        or result.request_sha256 != req.digest
        or result.captured_at < observed.captured_at
        or intent.configuration_sha256
        != hashlib.sha256(browser.configuration.model_dump_json().encode()).hexdigest()
        or (observed.task, observed.context_id, observed.attempt_id)
        != (trace.scope.task, trace.scope.context_id, trace.scope.attempt_id)
    ):
        raise EvidenceIntegrityError(
            "Reddit terminal page changed original browser/observation"
        )
    page = RedditPageHealth.model_validate_json(result.private_result)
    if page.model_dump_json() != result.private_result:
        raise EvidenceIntegrityError("Noncanonical original Reddit terminal page")
    active = tuple(t for t in observed.tabs if t.tab_id == observed.active_tab_id)
    if len(active) != 1:
        raise EvidenceIntegrityError(
            "Reddit terminal observation has no unique active document"
        )
    if page.status_source != "document_changed" and page.url != active[0].url:
        raise EvidenceIntegrityError(
            "Reddit terminal page is not the observed document"
        )
    return page
