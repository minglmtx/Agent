"""Original reset facts plus mandatory actual source/physical cleanup authority."""

from typing import Literal
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.task_finalization import TaskFinalizationAuthority
from lab_generate_skill.ports.state_qualification import StateQualificationChecks
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.adapters.plans.state_reads import StateReads
from .task_finalization_state import TaskFinalizationState


class FinalizationQualificationAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        state: TaskFinalizationState,
        source: TaskFinalizationAuthority,
        evidence: EvidenceReader,
    ) -> None:
        self.plan, self.declaration, self.state, self.source = (
            plan,
            declaration,
            state,
            source,
        )
        self.reads = StateReads(evidence)

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        s = self.state
        if (
            phase != "reset"
            or scope != self.declaration.scope
            or s.phase not in ("qualifying", "restored")
            or selection_ref != s.reset_selection_ref
            or s.reset_selection is None
            or self.reads.parse(
                selection_ref, "reset-selection/1", ResetSelection, control
            )
            != s.reset_selection
        ):
            raise OwnershipConflict(
                "Only original current complete reset facts are authorized"
            )
        self.source.verify(
            self.plan, self.declaration, tuple(s.references), operation, control
        )


class FinalizationResetAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        state: TaskFinalizationState,
        source: TaskFinalizationAuthority,
        checks: StateQualificationChecks,
        controls: OperationControls,
    ) -> None:
        self.plan, self.declaration, self.state, self.source = (
            plan,
            declaration,
            state,
            source,
        )
        self.checks, self.controls = checks, controls

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        raise OwnershipConflict(
            "Finalization grants no new baseline or Actor execution"
        )

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        control = self._current_reset(inputs, receipt, op)
        s = self.state
        assert s.reset_selection is not None and s.reset_selection_ref is not None
        actual = self.checks.reset(s.reset_selection, s.reset_selection_ref, control)
        if (
            inputs.plan,
            inputs.spec,
            inputs.task_recovery,
            inputs.environment_recovery,
            inputs.closures,
            inputs.task.checks,
            inputs.environment.checks,
            inputs.health.checks,
        ) != (
            actual.plan,
            actual.spec,
            actual.task_recovery,
            actual.environment_recovery,
            actual.closures,
            actual.task,
            actual.environment,
            actual.health,
        ):
            raise OwnershipConflict(
                "Complete original reset/health measurements changed"
            )
        control.checkpoint()

    def verify_reset_inputs(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        # reset_inputs is assigned only from this finalizer's completed
        # publish_reset_facts return. Its native checker has already run. The
        # source permission below is dynamic and must still run at each boundary.
        self._current_reset(inputs, receipt, op).checkpoint()

    def _current_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> OperationControl:
        s = self.state
        if (
            s.phase not in ("qualifying", "restored")
            or s.reset_selection is None
            or s.reset_selection_ref is None
            or inputs != s.reset_inputs
            or receipt != s.reset
            or s.closed is None
            or inputs.plan_ref != self.plan.reset_plan_ref
            or inputs.closure_refs != s.closed.closure_refs
        ):
            raise OwnershipConflict("Reset summary changed original finalization facts")
        control = self.controls.bind(op)
        self.source.verify(
            self.plan, self.declaration, tuple(s.references), op, control
        )
        return control
