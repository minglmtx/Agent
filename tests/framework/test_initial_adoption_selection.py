"""Real source/claim consumer in the formal wrapper layout; unit rights only.

Synthetic authority subclasses replace the kernel/installed-worker edge. They
never establish site, model, business or training permission.
"""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.ledger.stage_execution_authority import (
    StageExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.stage_validation_source import (
    SupervisedStageValidationSourceChecks,
    SupervisedStageValidationContexts,
)
from lab_generate_skill.bootstrap.current_initial_adoption import (
    stage_initial_adoption_checks,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from current_initial_adoption_fixtures import current_initial_case


def test_selected_layout_keeps_inner_outer_identity_and_live_claim_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = current_initial_case(tmp_path / "case")
    original = c.original
    outer = ClosedSourceContexts(
        original.contexts, original.source.source_context_receipt_ref
    )

    class UnitOwner(StageExecutionClaimAuthority):
        def __init__(self) -> None:
            self.contexts = outer
            self.origin = original.origin

    class UnitChecks(SupervisedStageValidationSourceChecks):
        def __init__(self) -> None:
            self.owner = UnitOwner()
            # Production places the supervised reader inside the site wrapper.
            self.contexts = cast(SupervisedStageValidationContexts, original.contexts)

        def load_source(
            self,
            plan: TaskExecutionPlan,
            op: OperationContext,
            control: OperationControl,
        ) -> ExecutionSourceFacts:
            return original.reader.load(plan, op, control)

        def verify_current(
            self,
            plan: TaskExecutionPlan,
            facts: ExecutionSourceFacts,
            op: OperationContext,
            control: OperationControl,
        ) -> None:
            original.reader.recheck(plan, facts, op, control)

    checks = UnitChecks()
    source = OriginalExecutionTaskSource(
        original.reader.plans,
        original.claims,
        outer,
        original.reader.bindings,
        c.records.store,
        source_checks=checks,
    )
    selected = stage_initial_adoption_checks(
        original.plan, c.receipt.scope, source, c.receipt.operation, c.records.controls
    )
    assert selected is not None and selected.inputs == c.inputs.adoption
    assert c.inputs.adoption is not None
    selected.verify_adoption(
        c.inputs.adoption,
        c.receipt.operation,
        c.records.controls.bind(c.receipt.operation),
    )
    monkeypatch.setattr(original.authority, "denied", "current")
    with pytest.raises(OwnershipConflict):
        selected.verify_adoption(
            c.inputs.adoption,
            c.receipt.operation,
            c.records.controls.bind(c.receipt.operation),
        )
