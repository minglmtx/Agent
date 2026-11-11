"""Group TaskCapture, original readonly judgment and independent record inputs."""

from collections.abc import Callable
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.retained_closure import (
    original_closed_browser,
)
from lab_generate_skill.adapters.sites.task_capture import RecordedTaskCapture
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceRequirements
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_capture import TaskCaptureInputs, TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControl,
    OperationControls,
    Clock,
)
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.ports.task_capture import TaskCaptureAuthority
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.trace_journal import TraceJournal
from lab_generate_skill.evaluators.gitlab.group import GroupEvaluator
from lab_generate_skill.sites.gitlab.tasks.group_capture_records import (
    GroupCaptureRecords,
)
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from .gitlab_group_evaluation import gitlab_group_evaluator
from .gitlab_group_captured import read_group_captured
from .gitlab_group_terminal import read_group_terminal
from .gitlab_group_task_initialization import GroupTaskInitialization


class RecordedGroupEvaluator:
    def __init__(
        self,
        selected: EvidenceRef,
        preparations: PreparationRecords,
        operation: OperationContext,
    ) -> None:
        self.selected, self.preparations, self.operation = (
            selected,
            preparations,
            operation,
        )

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return GroupEvaluator.requirements(contract)

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        self.requirements(contract)
        selected = read_group_captured(
            evidence,
            self.preparations,
            self.selected,
            contract,
            self.operation,
            control,
        )
        return gitlab_group_evaluator(selected).evaluate(contract, evidence, control)


class CapturedGroupEvaluator:
    def __init__(
        self, capture: RecordedTaskCapture, preparations: PreparationRecords
    ) -> None:
        self.capture, self.preparations = capture, preparations

    def requirements(self, contract: EvaluationContract) -> EvidenceRequirements:
        return GroupEvaluator.requirements(contract)

    def evaluate(
        self,
        contract: EvaluationContract,
        evidence: EvidenceReader,
        control: OperationControl,
    ) -> Evaluation:
        self.requirements(contract)
        c = self.capture
        if (
            c.plan.evaluation != contract
            or c.state.phase != "captured"
            or c.state.selection_ref is None
        ):
            raise OwnershipConflict("Original completed Group capture required")
        return RecordedGroupEvaluator(
            c.state.selection_ref, self.preparations, c.plan.operation
        ).evaluate(contract, evidence, control)


def gitlab_group_task_capture(
    plan: TaskExecutionPlan,
    declaration: TaskCapturePlan,
    declaration_ref: EvidenceRef,
    inputs: Callable[[OperationControl], TaskCaptureInputs],
    browser: Callable[[], RetainedBrowserResource],
    trace: Callable[[], TraceJournal],
    site: SiteHandle,
    site_spec: SiteResourceSpec,
    preparations: PreparationRecords,
    initialization: Callable[[], GroupTaskInitialization],
    authority: TaskCaptureAuthority,
    browser_authority: BrowserCaptureAuthority,
    site_authority: SiteCaptureAuthority,
    evidence: EvidenceStore,
    controls: OperationControls,
    clock: Clock,
) -> tuple[RecordedTaskCapture, CapturedGroupEvaluator]:
    plan = TaskExecutionPlan.model_validate(plan)
    declaration = TaskCapturePlan.model_validate(declaration)
    site_spec = SiteResourceSpec.model_validate(site_spec)
    group_initial_spec(declaration.scope.task)
    if (
        (
            declaration.page_collector_id,
            declaration.page_collector_version,
            declaration.guard_collector_id,
            declaration.guard_collector_version,
        )
        != ("gitlab-page-health", "1", "gitlab-group-creation", "1")
        or site_spec.configuration.site_id != "gitlab"
        or site_spec.configuration.private_evidence is None
        or site_spec.configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
    ):
        raise ValueError("Original Group collectors and native profile required")
    if any(
        value is None
        for value in (
            inputs,
            browser,
            trace,
            site,
            preparations,
            initialization,
            authority,
            browser_authority,
            site_authority,
            evidence,
            controls,
            clock,
        )
    ):
        raise ValueError("Original Group capture resources and authorities mandatory")
    writer = CaptureEvidence(evidence, "gitlab-group-task-records-v1")

    def publish(raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        try:
            return writer.put(raw, schema, control)
        except BaseException as error:
            setattr(error, "task_capture_record_candidates", tuple(writer.candidates))
            raise

    def current() -> GroupTaskInitialization:
        value = initialization()
        if not isinstance(value, GroupTaskInitialization) or value.plan != plan:
            raise OwnershipConflict("Original Group initialization producer required")
        return value

    def verify(
        ref: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None:
        read_group_terminal(
            evidence, preparations, ref, plan.evaluation, operation, control
        )

    def closed_record(control: OperationControl) -> EvidenceRef:
        held = browser()
        operation = held.operation.cleanup(
            declaration.close_operation_id + ".group-record",
            now=clock.utcnow(),
            seconds=plan.cleanup_seconds,
        )
        record = original_closed_browser(
            held.spec, held.operation, operation, held.journal, evidence, control
        )
        return publish(
            record.model_dump_json().encode(), record.schema_version, control
        )

    records = GroupCaptureRecords(
        publish,
        verify,
        lambda: current().native_before.pair(),
        lambda: current().declaration_ref,
        declaration_ref,
        closed_record,
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
        records,
        authority,
        browser_authority,
        site_authority,
        evidence,
        controls,
        clock,
    )
    evaluator = CapturedGroupEvaluator(capture, preparations)
    evaluator.requirements(plan.evaluation)
    return capture, evaluator
