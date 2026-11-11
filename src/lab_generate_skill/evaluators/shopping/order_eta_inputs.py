"""Join original Shopping task/native captures/page/sealed actual answer."""

from dataclasses import dataclass
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.sites.shopping.evidence_schema import (
    OrderEtaSpec,
    OrderEtaState,
    OrderEtaExecutionInput,
    OrderEtaEvidence,
    SiteCaptureEvidence,
    ShoppingPageHealth,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence
from lab_generate_skill.domain.errors import IncompleteAnswerEvidence
from lab_generate_skill.evaluators.browser_answer import (
    trace_answer,
)


@dataclass(frozen=True)
class EtaFacts:
    public: PublicTask
    spec: OrderEtaSpec
    before: OrderEtaState
    after: OrderEtaState
    page: ShoppingPageHealth
    answer: str | None


def load_eta_facts(
    contract: EvaluationContract,
    selection: OrderEtaEvidence,
    evidence: EvaluationEvidence,
) -> EtaFacts:
    if (
        selection.before is None
        or selection.after is None
        or selection.page is None
        or selection.trace_ref is None
    ):
        raise EvidenceNotFound("Required original Shopping capture/trace missing")
    binding = evidence.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
    public = evidence.read(
        contract.public_task_ref, "public-task/1", PublicTask, public=True
    )
    spec = evidence.read(
        contract.completion_spec_ref, "shopping-recorded-order-eta/1", OrderEtaSpec
    )
    if (
        binding.identity != contract.identity
        or public.identity != contract.identity
        or spec.task != contract.identity
        or binding.public_task_ref != contract.public_task_ref
        or binding.private_spec_ref != contract.completion_spec_ref
    ):
        raise EvidenceIntegrityError(
            "Shopping evaluation changed original selected task"
        )
    trace = evidence.read(
        selection.trace_ref,
        "interaction-trace/1",
        InteractionTrace,
        limit=16 * 1024 * 1024,
    )
    if (trace.scope.task, trace.scope.attempt_id) != (
        contract.identity,
        contract.attempt_id,
    ):
        raise EvidenceIntegrityError("Shopping trace belongs to another attempt")
    if trace.stop_reason in ("error", "uncertain", "cancelled"):
        raise IncompleteAnswerEvidence(
            "Original Actor execution did not finish cleanly"
        )

    def capture(pair: SiteCaptureEvidence) -> tuple[SiteCaptureIntent, OrderEtaState]:
        intent = evidence.read(
            pair.intent_ref, "site-capture-intent/2", SiteCaptureIntent
        )
        result = evidence.read(pair.result_ref, "site-task-result/1", SiteTaskResult)
        req = intent.request
        task = req.inspection
        op = req.operation
        if (
            (req.collector_id, req.collector_version) != ("shopping-order-eta", "1")
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
                "Shopping capture changed original task/attempt"
            )
        data = OrderEtaExecutionInput.model_validate_json(task.private_input)
        if data.model_dump_json() != task.private_input or data.spec != spec:
            raise EvidenceIntegrityError(
                "Shopping capture changed original private input"
            )
        state = OrderEtaState.model_validate_json(result.private_result)
        if state.model_dump_json() != result.private_result:
            raise EvidenceIntegrityError("Noncanonical original Shopping state")
        state.check(spec)
        return intent, state

    before_intent, before = capture(selection.before)
    after_intent, after = capture(selection.after)
    first, last = before_intent.request.inspection, after_intent.request.inspection
    if (
        before_intent.configuration_sha256 != after_intent.configuration_sha256
        or first.snapshot_ref != last.snapshot_ref
        or first.private_input != last.private_input
        or first.operation.allocation_id != last.operation.allocation_id
        or first.operation.recovery_ref != last.operation.recovery_ref
        or first.operation.operation_id == last.operation.operation_id
    ):
        raise EvidenceIntegrityError(
            "Shopping captures changed original instance/snapshot/operation"
        )
    page_intent = evidence.read(
        selection.page.intent_ref, "browser-capture-intent/1", BrowserCaptureIntent
    )
    page_result = evidence.read(
        selection.page.result_ref, "browser-capture-result/1", BrowserCaptureResult
    )
    req = page_intent.request
    observed = evidence.read(
        trace.final_observation_ref, "observation/1", Observation, public=True
    )
    if (
        req.scope != trace.scope
        or req.observation_sha256 != trace.final_observation_ref.sha256
        or (req.collector_id, req.collector_version) != ("shopping-page-health", "1")
        or page_result.request_sha256 != req.digest
        or page_result.captured_at < observed.captured_at
        or (observed.task, observed.context_id, observed.attempt_id)
        != (trace.scope.task, trace.scope.context_id, trace.scope.attempt_id)
    ):
        raise EvidenceIntegrityError(
            "Shopping page differs from original final observation"
        )
    page = ShoppingPageHealth.model_validate_json(page_result.private_result)
    if page.model_dump_json() != page_result.private_result:
        raise EvidenceIntegrityError("Noncanonical original Shopping terminal page")
    answer = trace_answer(trace, public, evidence)
    return EtaFacts(public, spec, before, after, page, answer)
