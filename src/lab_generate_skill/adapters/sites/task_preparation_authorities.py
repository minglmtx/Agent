"""Exact producer facts plus mandatory external construction/source admission.

These narrow authorities qualify environment/preparation publication only. They
cannot authorize Actor execution, reset, a new native call or a source claim.
"""

from typing import Literal
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.task_preparation import TaskPreparationAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_preparation_state import TaskPreparationState
from .task_preparation_evidence import TaskPreparationEvidence


class PreparationEnvironmentAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        state: TaskPreparationState,
        io: TaskPreparationEvidence,
        authority: TaskPreparationAuthority,
    ) -> None:
        self.plan, self.declaration, self.state, self.io, self.authority = (
            plan,
            declaration,
            state,
            io,
            authority,
        )

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        d, s = self.declaration, self.state
        if (
            phase != "environment"
            or s.phase not in ("preparing", "prepared")
            or scope != d.scope
            or (selection_ref != s.environment_selection_ref or s.snapshot_ref is None)
        ):
            raise OwnershipConflict(
                "Only original current preparation environment is authorized"
            )
        value = EnvironmentSelection.model_validate_json(
            self.io.read(selection_ref, control)
        )
        if (
            value.scope,
            value.site_spec_ref,
            value.site_started_ref,
            value.snapshot_ref,
        ) != (
            d.scope,
            d.site_spec_ref,
            s.original_acquired().site_started_ref,
            s.snapshot_ref,
        ):
            raise OwnershipConflict(
                "Environment changed original snapshot/site lineage"
            )
        self.authority.verify(self.plan, d, operation, control)
        control.checkpoint()


class PreparationPublicationAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        state: TaskPreparationState,
        authority: TaskPreparationAuthority,
    ) -> None:
        self.plan, self.declaration, self.state, self.authority = (
            plan,
            declaration,
            state,
            authority,
        )

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        s, d = self.state, self.declaration
        if s.phase not in ("preparing", "prepared") or (
            inputs.request != s.prepare_request
            or inputs.result != s.prepare_result
            or inputs.environment != s.environment
            or checks.status != "pass"
            or inputs.selection.request_ref != s.prepare_request_ref
            or inputs.selection.result_ref != s.prepare_result_ref
            or inputs.selection.environment_ref != s.environment_ref
        ):
            raise OwnershipConflict(
                "Publication changed original completed preparation facts"
            )
        self.authority.verify(self.plan, d, op, control)
        control.checkpoint()
