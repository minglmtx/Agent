"""Bind the chosen captured facts to original task, source and sealed execution."""

from dataclasses import dataclass
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    ProductDescriptionSpec,
    ProductCatalogState,
    AdminPageHealth,
    ProductDescriptionEvidence,
    SiteCaptureEvidence,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence


class IncompleteExecution(ValueError):
    """Original runtime failure or missing target, matching legacy unknown semantics."""


@dataclass(frozen=True)
class DescriptionFacts:
    public: PublicTask
    spec: ProductDescriptionSpec
    before: ProductCatalogState
    after: ProductCatalogState
    page: AdminPageHealth


def load_description_facts(
    contract: EvaluationContract,
    selection: ProductDescriptionEvidence,
    evidence: EvaluationEvidence,
) -> DescriptionFacts:
    if (
        selection.before is None
        or selection.after is None
        or selection.page is None
        or selection.trace_ref is None
    ):
        raise EvidenceNotFound("Required selected capture or sealed trace missing")
    binding = evidence.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
    public = evidence.read(
        contract.public_task_ref, "public-task/1", PublicTask, public=True
    )
    spec = evidence.read(
        contract.completion_spec_ref,
        "shopping-admin-product-description/1",
        ProductDescriptionSpec,
    )
    if (
        binding.identity != contract.identity
        or public.identity != contract.identity
        or spec.task != contract.identity
        or binding.public_task_ref != contract.public_task_ref
        or binding.private_spec_ref != contract.completion_spec_ref
        or spec.store_id != 0
    ):
        raise EvidenceIntegrityError(
            "Evaluation changed original task meaning or selected store"
        )
    trace = evidence.read(
        selection.trace_ref,
        "interaction-trace/1",
        InteractionTrace,
        limit=16 * 1024 * 1024,
    )
    if (
        trace.scope.task != contract.identity
        or trace.scope.attempt_id != contract.attempt_id
    ):
        raise EvidenceIntegrityError("Evaluation trace belongs to another attempt")
    if trace.stop_reason in ("cancelled", "error", "uncertain"):
        raise IncompleteExecution(
            "Original execution did not produce a valid completed attempt"
        )

    def catalog(
        pair: SiteCaptureEvidence,
    ) -> tuple[SiteCaptureIntent, ProductCatalogState]:
        intent = evidence.read(
            pair.intent_ref, "site-capture-intent/2", SiteCaptureIntent
        )
        result = evidence.read(pair.result_ref, "site-task-result/1", SiteTaskResult)
        req = intent.request
        task, op = req.inspection, req.operation
        if (
            (req.collector_id, req.collector_version) != ("admin-product-catalog", "1")
            or result.request_sha256 != req.digest
            or task.binding_ref != contract.task_contract_ref
            or task.task != contract.identity
            or (op.run_id, op.owner_id, op.attempt_id)
            != (
                trace.scope.owner.run_id,
                trace.scope.owner.owner_id,
                trace.scope.attempt_id,
            )
        ):
            raise EvidenceIntegrityError(
                "Product capture changed selected original task/attempt"
            )
        state = ProductCatalogState.model_validate_json(result.private_result)
        if (state.product_id, state.store_id) != (spec.product_id, spec.store_id):
            raise EvidenceIntegrityError("Product capture changed original target")
        if state.target_record_json is None:
            raise IncompleteExecution(
                "Original evaluator requires exactly one before/after target"
            )
        return intent, state

    before_intent, before = catalog(selection.before)
    after_intent, after = catalog(selection.after)
    before_task, after_task = (
        before_intent.request.inspection,
        after_intent.request.inspection,
    )
    if (
        before_intent.configuration_sha256 != after_intent.configuration_sha256
        or before_task.snapshot_ref != after_task.snapshot_ref
        or before_task.private_input != after_task.private_input
        or before_task.operation.allocation_id != after_task.operation.allocation_id
        or before_task.operation.operation_id == after_task.operation.operation_id
    ):
        raise EvidenceIntegrityError(
            "Before/after captures changed original instance or reused operation"
        )
    page_intent = evidence.read(
        selection.page.intent_ref, "browser-capture-intent/1", BrowserCaptureIntent
    )
    page_result = evidence.read(
        selection.page.result_ref, "browser-capture-result/1", BrowserCaptureResult
    )
    req_page = page_intent.request
    observed = evidence.read(
        trace.final_observation_ref, "observation/1", Observation, public=True
    )
    if (
        req_page.scope != trace.scope
        or req_page.observation_sha256 != trace.final_observation_ref.sha256
        or (req_page.collector_id, req_page.collector_version)
        != ("admin-page-health", "1")
        or page_result.request_sha256 != req_page.digest
        or page_result.captured_at < observed.captured_at
    ):
        raise EvidenceIntegrityError(
            "Page capture differs from final original observation"
        )
    if (observed.task, observed.context_id, observed.attempt_id) != (
        trace.scope.task,
        trace.scope.context_id,
        trace.scope.attempt_id,
    ):
        raise EvidenceIntegrityError("Final observation changed original scope")
    page = AdminPageHealth.model_validate_json(page_result.private_result)
    return DescriptionFacts(public, spec, before, after, page)
