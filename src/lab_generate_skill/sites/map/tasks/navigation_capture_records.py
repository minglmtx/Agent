"""Original navigation terminal/outer selection on existing evidence contracts."""

from collections.abc import Callable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.map_navigation_terminal import (
    MapNavigationTerminalSelection,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from ..evidence_schema import MapNavigationEvidence, MapCapturePair

Publish = Callable[[bytes, str, OperationControl], EvidenceRef]
VerifyTerminal = Callable[[EvidenceRef, OperationContext, OperationControl], None]


class NavigationCaptureRecords:
    def __init__(self, publish: Publish, verify: VerifyTerminal) -> None:
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
        record = MapNavigationTerminalSelection(
            initial=inputs.initial,
            initial_evidence=MapInitialEvidence(
                intent_ref=inputs.initial_capture_intent_ref,
                result_ref=inputs.initial_capture_result_ref,
            ),
            initial_checks_ref=inputs.initial_checks_ref,
            terminal_return_ref=return_ref,
            capture_intent_ref=intent_ref,
            capture_result_ref=result_ref,
            trace_ref=trace_ref,
            trace_snapshot_ref=snapshot_ref,
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
        selected = MapNavigationEvidence(
            environment_ref=inputs.environment_selection_ref,
            terminal_ref=terminal_ref,
            final_guard=MapCapturePair(
                intent_ref=guard_intent_ref, result_ref=guard_result_ref
            ),
            browser_closure_ref=closure_ref,
        )
        return self.publish(
            selected.model_dump_json().encode(), selected.schema_version, control
        )
