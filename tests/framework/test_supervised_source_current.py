"""Actual source-check adapter/current-claim composition with declared kernel/store doubles."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedExecutionTaskSourceChecks,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_phase_fixtures import phase_case
from test_closed_source_read_protocol import original_material


@pytest.mark.parametrize(
    "fault", ["none", "owner", "storage", "claim", "scope", "plan"]
)
def test_actual_source_recheck_adapter_keeps_live_owner_material_storage_claim(
    tmp_path: Path, fault: str
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    plan = c.plan
    source = c.source.source_reader
    op = plan.read_operation
    control = c.deps.controls.bind(op)
    facts = source.load(plan, op, control)
    material, _ = original_material()

    class Caller(OriginalExecutionClaimAuthority):
        calls = 0

        def __init__(self) -> None:
            self.run, self.task = facts.source.run, facts.source.task

        def require_caller(self, operation: OperationContext) -> None:
            self.calls += 1
            if fault == "owner":
                raise OwnershipConflict("Original current caller revoked")

    class Transport(ClosedSourceReadTransport):
        material_checks = 0
        storage_checks = 0

        def __init__(self) -> None:
            pass

        def require_current(
            self, selected: ClosedSourceMaterial, operation: OperationContext
        ) -> None:
            self.material_checks += 1
            assert selected == material and operation == op

        def check_current(self, bounded: OperationControl) -> None:
            bounded.checkpoint()
            self.storage_checks += 1
            if fault == "storage":
                raise PermissionError("Current original storage gate revoked")

    owner, transport = Caller(), Transport()
    source.source_checks = SupervisedExecutionTaskSourceChecks(
        owner, material, transport
    )
    if fault == "claim":
        c.source.claim_authority.denied = True
    elif fault == "scope":
        op = op.model_copy(update={"owner_id": "foreign"})
    elif fault == "plan":
        plan = plan.model_copy(
            update={
                "skill_ref": plan.skill_ref.model_copy(update={"producer": "foreign"})
            }
        )
    if fault == "none":
        source.recheck(plan, facts, op, control)
        source.recheck(plan, facts, op, control)
        assert (
            owner.calls == 4
            and transport.material_checks == transport.storage_checks == 2
        )
    else:
        with pytest.raises(
            PermissionError if fault == "storage" else OwnershipConflict
        ):
            source.recheck(plan, facts, op, control)
    assert c.model.calls == c.browser.calls == 0 and not c.phases.calls
