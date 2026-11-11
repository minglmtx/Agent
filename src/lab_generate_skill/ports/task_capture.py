"""Subordinate record/permission capabilities for the existing TaskCapture port."""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCapturePlan, TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .lifecycle import OperationControl


class TaskCaptureAuthority(Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskCapturePlan,
        inputs: TaskCaptureInputs,
        snapshot: TraceSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Original current run/claim/source/resource/trace and fixed collector rights.

        Terminal collection may delegate original browser closure once. This
        grants neither restoration nor replacement/replay of unknown requests.
        """
        ...


class TaskCaptureRecords(Protocol):
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
    ) -> EvidenceRef: ...
    def verify_terminal(
        self, ref: EvidenceRef, operation: OperationContext, control: OperationControl
    ) -> None: ...
    def selection(
        self,
        inputs: TaskCaptureInputs,
        terminal_ref: EvidenceRef,
        closure_ref: EvidenceRef,
        guard_intent_ref: EvidenceRef,
        guard_result_ref: EvidenceRef,
        control: OperationControl,
    ) -> EvidenceRef: ...
