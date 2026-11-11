"""Original category pre-close selection and complete post-close guard selection."""

from collections.abc import Callable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..navigation_evidence import CategoryNavigationEvidence
from ..evidence_schema import PageCaptureEvidence, SiteCaptureEvidence

Publish = Callable[[bytes, str, OperationControl], EvidenceRef]
Read = Callable[[EvidenceRef, OperationControl], CategoryNavigationEvidence]
Verify = Callable[[EvidenceRef, OperationContext, OperationControl], None]


class CategoryNavigationCaptureRecords:
    def __init__(self, publish: Publish, read: Read, verify: Verify) -> None:
        self.publish, self.read, self.verify = publish, read, verify

    @staticmethod
    def _inputs(inputs: TaskCaptureInputs) -> TaskCaptureInputs:
        inputs = TaskCaptureInputs.model_validate(inputs)
        task = inputs.initialized.actor.scope.task
        if (task.site, task.family, task.contract_version, task.split) != (
            "shopping",
            "page_navigation",
            1,
            "train",
        ):
            raise OwnershipConflict("Original category capture inputs required")
        return inputs

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
        inputs = self._inputs(inputs)
        control.checkpoint()
        selected = CategoryNavigationEvidence(
            environment_ref=inputs.environment_selection_ref,
            initial=inputs.initial,
            initial_checks_ref=inputs.initial_checks_ref,
            trace_ref=trace_ref,
            trace_snapshot_ref=snapshot_ref,
            terminal_return_ref=return_ref,
            page=PageCaptureEvidence(intent_ref=intent_ref, result_ref=result_ref),
            final_guard=None,
            browser_closure_ref=None,
        )
        return self.publish(
            selected.model_dump_json().encode(), selected.schema_version, control
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
        inputs = self._inputs(inputs)
        old = self.read(terminal_ref, control)
        if (
            old.environment_ref != inputs.environment_selection_ref
            or old.initial != inputs.initial
            or old.initial_checks_ref != inputs.initial_checks_ref
            or any(
                value is None
                for value in (
                    old.trace_ref,
                    old.trace_snapshot_ref,
                    old.terminal_return_ref,
                    old.page,
                )
            )
            or old.final_guard is not None
            or old.browser_closure_ref is not None
        ):
            raise OwnershipConflict(
                "Category selection changed original pre-close facts"
            )
        selected = CategoryNavigationEvidence.model_validate(
            old.model_copy(
                update={
                    "browser_closure_ref": closure_ref,
                    "final_guard": SiteCaptureEvidence(
                        intent_ref=guard_intent_ref, result_ref=guard_result_ref
                    ),
                }
            )
        )
        return self.publish(
            selected.model_dump_json().encode(), selected.schema_version, control
        )
