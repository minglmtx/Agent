"""Category records on the original TaskCapture, browser owner and native guard."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.domain.evaluation import Evaluation, EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_capture import TaskCaptureInputs, TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.ports.task_capture import TaskCaptureAuthority
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.sites.shopping.navigation_evidence import (
    CategoryNavigationEvidence,
)
from lab_generate_skill.sites.shopping.tasks.navigation_capture_records import (
    CategoryNavigationCaptureRecords,
)
from lab_generate_skill.evaluators.shopping.navigation import (
    CategoryNavigationEvaluator,
)
from .shopping_category_evaluation import (
    shopping_category_evaluator,
    shopping_category_evidence_reader,
)


class CapturedCategoryNavigationEvaluator:
    def __init__(
        self, capture: RecordedTaskCapture, preparations: PreparationRecords
    ) -> None:
        self.capture, self.preparations = capture, preparations

    def _original(
        self, selected: CategoryNavigationEvidence
    ) -> CategoryNavigationEvaluator:
        c = self.capture
        return shopping_category_evaluator(
            selected, self.preparations, c.site_spec, c.site.site, c.plan.operation
        )

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return CategoryNavigationEvaluator.requirements(contract)

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        self.requirements(contract)
        c = self.capture
        if (
            contract != c.plan.evaluation
            or c.state.phase != "captured"
            or c.state.selection_ref is None
        ):
            raise OwnershipConflict(
                "Original successful task capture required before evaluation"
            )
        selected = c.reads.parse(
            c.state.selection_ref,
            "shopping-category-navigation-evidence/1",
            CategoryNavigationEvidence,
            control,
        )
        return self._original(selected).evaluate(contract, evidence, control)


def shopping_category_task_capture(
    plan: TaskExecutionPlan,
    declaration: TaskCapturePlan,
    declaration_ref: EvidenceRef,
    inputs: Callable[[OperationControl], TaskCaptureInputs],
    browser: Callable[[], RetainedBrowserResource],
    trace: Callable[[], TraceJournal],
    site: SiteHandle,
    site_spec: SiteResourceSpec,
    preparations: PreparationRecords,
    authority: TaskCaptureAuthority,
    browser_authority: BrowserCaptureAuthority,
    site_authority: SiteCaptureAuthority,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
) -> tuple[RecordedTaskCapture, CapturedCategoryNavigationEvaluator]:
    if (
        declaration.page_collector_id,
        declaration.page_collector_version,
        declaration.guard_collector_id,
        declaration.guard_collector_version,
    ) != (
        "shopping-category-navigation-page",
        "1",
        "shopping-category-navigation",
        "1",
    ):
        raise ValueError("Original selected navigation collectors required")
    writer = CaptureEvidence(evidence, "shopping-category-task-records-v1")

    def publish(raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        try:
            return writer.put(raw, schema, control)
        except BaseException as error:
            setattr(error, "task_capture_record_candidates", tuple(writer.candidates))
            raise

    def read(ref: EvidenceRef, control: OperationControl) -> CategoryNavigationEvidence:
        from lab_generate_skill.evaluators.evidence import EvaluationEvidence

        return EvaluationEvidence(evidence, control).read(
            ref, "shopping-category-navigation-evidence/1", CategoryNavigationEvidence
        )

    def verify(
        ref: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None:
        selected = read(ref, control)
        shopping_category_evidence_reader(
            preparations, site_spec, site.site, operation
        ).verify_terminal(plan.evaluation, selected, evidence, control)

    capture = RecordedTaskCapture(
        plan,
        declaration,
        declaration_ref,
        inputs,
        browser,
        trace,
        site,
        site_spec,
        preparations,
        CategoryNavigationCaptureRecords(publish, read, verify),
        authority,
        browser_authority,
        site_authority,
        evidence,
        controls,
        clock,
    )
    evaluator = CapturedCategoryNavigationEvaluator(capture, preparations)
    evaluator.requirements(plan.evaluation)
    return capture, evaluator
