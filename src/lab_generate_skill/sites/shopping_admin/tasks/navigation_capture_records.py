"""Original navigation terminal/closure/guard selections on common capture ports."""

from collections.abc import Callable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from ..navigation_terminal_schema import (
    AdminNavigationTerminalSelection,
    AdminNavigationCapturedEvidence,
)

Publish = Callable[[bytes, str, OperationControl], EvidenceRef]
Verify = Callable[[EvidenceRef, OperationContext, OperationControl], None]


class NavigationCaptureRecords:
    def __init__(self, publish: Publish, verify: Verify) -> None:
        self.publish, self.verify = publish, verify

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
        record = AdminNavigationTerminalSelection(
            scope=inputs.initialized.actor.scope,
            initial=inputs.initial,
            initial_checks_ref=inputs.initial_checks_ref,
            initial_capture_intent_ref=inputs.initial_capture_intent_ref,
            initial_capture_result_ref=inputs.initial_capture_result_ref,
            trace_ref=trace_ref,
            trace_snapshot_ref=snapshot_ref,
            terminal_return_ref=return_ref,
            page_intent_ref=intent_ref,
            page_result_ref=result_ref,
            prepare_request_ref=inputs.prepare_request_ref,
            environment_selection_ref=inputs.environment_selection_ref,
        )
        return self.publish(
            record.model_dump_json().encode(), record.schema_version, control
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
        record = AdminNavigationCapturedEvidence(
            scope=inputs.initialized.actor.scope,
            terminal_ref=terminal_ref,
            browser_closure_ref=closure_ref,
            guard_intent_ref=guard_intent_ref,
            guard_result_ref=guard_result_ref,
        )
        return self.publish(
            record.model_dump_json().encode(), record.schema_version, control
        )
