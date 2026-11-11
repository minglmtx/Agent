"""Admin navigation binding of original terminal/close/native capture consumers."""

from collections.abc import Callable
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.sites.task_terminal_inputs import (
    TaskTerminalEvidenceInputs,
)
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.ports.task_capture import TaskCaptureAuthority
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.sites.shopping_admin.tasks.navigation_capture_records import (
    NavigationCaptureRecords,
)
from lab_generate_skill.evaluators.shopping_admin.navigation import (
    AdminNavigationEvaluator,
)
from .admin_navigation_terminal import read_admin_navigation_terminal
from .admin_navigation_captured import read_admin_navigation_captured


class RecordedAdminNavigationEvaluator:
    """Original immutable inputs usable in a separate readonly process."""

    def __init__(
        self,
        selected: EvidenceRef,
        preparations: PreparationRecords,
        operation: OperationContext,
        *,
        initials: InitialObservationReads | None = None,
    ) -> None:
        self.selected, self.preparations, self.operation = (
            selected,
            preparations,
            operation,
        )
        self.initials = initials

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return AdminNavigationEvaluator.requirements(contract)

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        self.requirements(contract)
        selected = read_admin_navigation_captured(
            evidence,
            self.preparations,
            self.selected,
            contract,
            self.operation,
            control,
            initials=self.initials,
        )
        return AdminNavigationEvaluator(selected).evaluate(contract, evidence, control)


class CapturedAdminNavigationEvaluator:
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

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return AdminNavigationEvaluator.requirements(contract)

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
            raise OwnershipConflict("Original successful navigation capture required")
        evaluator = RecordedAdminNavigationEvaluator(
            c.state.selection_ref,
            self.preparations,
            c.plan.operation,
            initials=self.initials,
        )
        if self.terminal_inputs is None:
            return evaluator.evaluate(contract, evidence, control)
        with self.terminal_inputs.inputs(evidence, c.plan.operation, control) as passed:
            return evaluator.evaluate(contract, passed, control)


def admin_navigation_task_capture(
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
) -> tuple[RecordedTaskCapture, CapturedAdminNavigationEvaluator]:
    if (
        (
            declaration.page_collector_id,
            declaration.page_collector_version,
            declaration.guard_collector_id,
            declaration.guard_collector_version,
        )
        != ("admin-navigation-page", "1", "admin-navigation-snapshot-integrity", "1")
        or site_spec.configuration.site_id != "shopping_admin"
        or site_spec.configuration.schema_version != "site-worker-configuration/7"
    ):
        raise ValueError(
            "Explicit original version7 navigation collectors/resource required"
        )
    if any(
        v is None
        for v in (
            inputs,
            browser,
            trace,
            site,
            preparations,
            authority,
            browser_authority,
            site_authority,
            evidence,
            controls,
            clock,
        )
    ):
        raise ValueError("Original navigation resources and permissions are mandatory")
    writer = CaptureEvidence(evidence, "admin-navigation-task-records-v1")

    def publish(raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        try:
            return writer.put(raw, schema, control)
        except BaseException as error:
            setattr(error, "task_capture_record_candidates", tuple(writer.candidates))
            raise

    def verify(
        reference: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None:
        if terminal_inputs is not None:
            terminal_inputs.verify(reference, operation, control)
            return
        read_admin_navigation_terminal(
            evidence,
            preparations,
            reference,
            plan.evaluation,
            operation,
            control,
            initials=initials,
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
    evaluator = CapturedAdminNavigationEvaluator(
        capture, preparations, initials, terminal_inputs
    )
    evaluator.requirements(plan.evaluation)
    return capture, evaluator
