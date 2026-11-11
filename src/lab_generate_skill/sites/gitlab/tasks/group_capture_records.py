"""Group terminal and final guard records on the existing TaskCapture port."""

from collections.abc import Callable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from ..evidence_schema import GitlabSiteCapture, GitlabPageCapture
from ..group_terminal_schema import GroupTerminalSelection, GroupCapturedSelection


class GroupCaptureRecords:
    def __init__(
        self,
        publish: Callable[[bytes, str, OperationControl], EvidenceRef],
        verify: Callable[[EvidenceRef, OperationContext, OperationControl], None],
        before: Callable[[], GitlabSiteCapture],
        declaration: Callable[[], EvidenceRef],
        capture_plan_ref: EvidenceRef,
        closed_record: Callable[[OperationControl], EvidenceRef],
    ) -> None:
        self.publish, self.verify, self.before, self.declaration = (
            publish,
            verify,
            before,
            declaration,
        )
        self.capture_plan_ref, self.closed_record = capture_plan_ref, closed_record

    def terminal(
        self,
        inputs: TaskCaptureInputs,
        trace_ref: EvidenceRef,
        snapshot_ref: EvidenceRef,
        return_ref: EvidenceRef,
        intent_ref: EvidenceRef,
        result_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EvidenceRef:
        selection = GroupTerminalSelection(
            scope=inputs.initialized.actor.scope,
            initialization_plan_ref=self.declaration(),
            initial=inputs.initial,
            capture_plan_ref=self.capture_plan_ref,
            initialized=inputs.initialized,
            initial_checks_ref=inputs.initial_checks_ref,
            initial_page=GitlabPageCapture(
                intent_ref=inputs.initial_capture_intent_ref,
                result_ref=inputs.initial_capture_result_ref,
            ),
            before=self.before(),
            trace_ref=trace_ref,
            trace_snapshot_ref=snapshot_ref,
            terminal_return_ref=return_ref,
            page=GitlabPageCapture(intent_ref=intent_ref, result_ref=result_ref),
            prepare_request_ref=inputs.prepare_request_ref,
            environment_selection_ref=inputs.environment_selection_ref,
        )
        return self.publish(
            selection.model_dump_json().encode(), selection.schema_version, control
        )

    def verify_terminal(
        self, ref: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None:
        self.verify(ref, operation, control)

    def selection(
        self,
        inputs: TaskCaptureInputs,
        terminal_ref: EvidenceRef,
        closure_ref: EvidenceRef,
        guard_intent_ref: EvidenceRef,
        guard_result_ref: EvidenceRef,
        control: OperationControl,
    ) -> EvidenceRef:
        selection = GroupCapturedSelection(
            scope=inputs.initialized.actor.scope,
            terminal_ref=terminal_ref,
            browser_closure_ref=closure_ref,
            browser_record_ref=self.closed_record(control),
            after=GitlabSiteCapture(
                intent_ref=guard_intent_ref, result_ref=guard_result_ref
            ),
        )
        return self.publish(
            selection.model_dump_json().encode(), selection.schema_version, control
        )
