"""Read original task/trace/browser/final active page without new actions."""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.sites.shopping_admin.evidence_schema import (
    AdminNavigationEvidence,
    AdminNavigationSpec,
    AdminNavigationPage,
)
from lab_generate_skill.evaluators.evidence import EvaluationEvidence


class IncompleteNavigationExecution(ValueError):
    """Original Actor did not complete a valid first request/terminal trace."""


@dataclass(frozen=True)
class NavigationFacts:
    public: PublicTask
    spec: AdminNavigationSpec
    page: AdminNavigationPage


def load_navigation_facts(
    contract: EvaluationContract,
    selected: AdminNavigationEvidence,
    evidence: EvaluationEvidence,
) -> NavigationFacts:
    if (
        selected.trace_ref is None
        or selected.page_intent_ref is None
        or selected.page_result_ref is None
    ):
        raise EvidenceNotFound("Required original navigation terminal evidence missing")
    binding = evidence.read(contract.task_contract_ref, "task-binding/1", TaskBinding)
    public = evidence.read(
        contract.public_task_ref, "public-task/1", PublicTask, public=True
    )
    spec = evidence.read(
        contract.completion_spec_ref,
        "shopping-admin-page-navigation/1",
        AdminNavigationSpec,
    )
    if (
        (binding.identity, public.identity, spec.task, selected.scope.task)
        != (contract.identity,) * 4
        or selected.scope.attempt_id != contract.attempt_id
        or (binding.public_task_ref, binding.private_spec_ref)
        != (contract.public_task_ref, contract.completion_spec_ref)
    ):
        raise EvidenceIntegrityError("Navigation changed original task/source/attempt")
    trace = evidence.read(
        selected.trace_ref,
        "interaction-trace/1",
        InteractionTrace,
        limit=16 * 1024 * 1024,
    )
    if trace.scope != selected.scope:
        raise EvidenceIntegrityError("Navigation trace changed original scope")
    if (
        trace.stop_reason in ("cancelled", "error", "uncertain")
        or trace.generations < 1
    ):
        raise IncompleteNavigationExecution(
            "Original navigation Actor request/trace incomplete"
        )
    browser = evidence.read(
        selected.browser_spec_ref, "browser-resource-spec/4", BrowserResourceSpec
    )
    config = browser.configuration
    initialization = config.initialization
    if (
        config.spec.scope != trace.scope
        or config.spec.task != public
        or not isinstance(initialization, AdminNavigationInitialization)
        or (initialization.native_contract_sha256, initialization.start_path)
        != (spec.native_contract_ref.sha256, spec.start_path)
    ):
        raise EvidenceIntegrityError(
            "Navigation browser changed original source/start/configuration"
        )
    intent = evidence.read(
        selected.page_intent_ref, "browser-capture-intent/1", BrowserCaptureIntent
    )
    result = evidence.read(
        selected.page_result_ref, "browser-capture-result/1", BrowserCaptureResult
    )
    observed = evidence.read(
        trace.final_observation_ref, "observation/1", Observation, public=True
    )
    req = intent.request
    if (
        req.scope != trace.scope
        or req.observation_sha256 != trace.final_observation_ref.sha256
        or (req.collector_id, req.collector_version) != ("admin-navigation-page", "1")
        or result.request_sha256 != req.digest
        or result.captured_at < observed.captured_at
        or intent.configuration_sha256
        != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
    ):
        raise EvidenceIntegrityError(
            "Navigation capture changed final original observation/configuration"
        )
    if (observed.task, observed.context_id, observed.attempt_id) != (
        trace.scope.task,
        trace.scope.context_id,
        trace.scope.attempt_id,
    ):
        raise EvidenceIntegrityError(
            "Navigation final observation changed original scope"
        )
    page = AdminNavigationPage.model_validate_json(result.private_result)
    if page.model_dump_json() != result.private_result:
        raise EvidenceIntegrityError("Navigation terminal page is not canonical")
    active = [tab for tab in observed.tabs if tab.tab_id == observed.active_tab_id]
    if len(active) != 1 or active[0].url != page.url:
        raise EvidenceIntegrityError("Navigation capture changed original active page")
    return NavigationFacts(public, spec, page)
