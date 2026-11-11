"""Bind existing TaskCapture/Evaluator ports to the original navigation records."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_terminal_inputs import (
    TaskTerminalEvidenceInputs,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
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
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.sites.map.evidence_schema import MapNavigationEvidence
from lab_generate_skill.sites.map.tasks.navigation_capture_records import (
    NavigationCaptureRecords,
)
from lab_generate_skill.evaluators.map.navigation import NavigationEvaluator
from .map_navigation_evaluation import map_navigation_evaluator
from .map_navigation_terminal import read_map_navigation_terminal


class CapturedNavigationEvaluator:
    def __init__(
        self,
        capture: RecordedTaskCapture,
        preparations: PreparationRecords,
        initials: InitialObservationReads | None = None,
        terminal_inputs: TaskTerminalEvidenceInputs | None = None,
    ) -> None:
        self.capture, self.preparations = capture, preparations
        self.initials = initials
        self.terminal_inputs = terminal_inputs

    def _original(self, selected: MapNavigationEvidence) -> NavigationEvaluator:
        c = self.capture
        return map_navigation_evaluator(
            selected,
            self.preparations,
            c.site_spec,
            c.site.site,
            c.plan.operation,
            initials=self.initials,
        )

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return NavigationEvaluator.requirements(contract)

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
        if self.terminal_inputs is None:
            return self._evaluate(contract, evidence, control)
        with self.terminal_inputs.inputs(evidence, c.plan.operation, control) as passed:
            return self._evaluate(contract, passed, control)

    def _evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        c = self.capture
        assert c.state.selection_ref is not None
        selected = StateReads(evidence).parse(
            c.state.selection_ref,
            "map-navigation-evidence/1",
            MapNavigationEvidence,
            control,
        )
        return self._original(selected).evaluate(contract, evidence, control)


def map_navigation_task_capture(
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
    *,
    initials: InitialObservationReads | None = None,
    terminal_inputs: TaskTerminalEvidenceInputs | None = None,
) -> tuple[RecordedTaskCapture, CapturedNavigationEvaluator]:
    if (
        declaration.page_collector_id,
        declaration.page_collector_version,
        declaration.guard_collector_id,
        declaration.guard_collector_version,
    ) != ("map-navigation-page-health", "1", "map-navigation-state", "1"):
        raise ValueError("Original selected navigation collectors required")
    writer = CaptureEvidence(evidence, "map-navigation-task-records-v1")

    def publish(raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        try:
            return writer.put(raw, schema, control)
        except BaseException as error:
            setattr(error, "task_capture_record_candidates", tuple(writer.candidates))
            raise

    def verify(
        ref: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None:
        if terminal_inputs is not None:
            terminal_inputs.verify(ref, operation, control)
            return
        read_map_navigation_terminal(
            evidence, preparations, ref, operation, control, initials=initials
        )

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
        NavigationCaptureRecords(publish, verify),
        authority,
        browser_authority,
        site_authority,
        evidence,
        controls,
        clock,
        initials=initials,
    )
    evaluator = CapturedNavigationEvaluator(
        capture, preparations, initials, terminal_inputs
    )
    evaluator.requirements(plan.evaluation)
    return capture, evaluator
