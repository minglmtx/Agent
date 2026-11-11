"""Actual plans/CAS with explicit test authority; no real writer authorization."""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import AttemptBinding, RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_evidence_run_plans import persisted_plan
from test_run_journal import CancelSwitch
from test_run_plan import binding as plan_binding


def operation(
    binding: SourceClaimBinding, *, attempt: str | None = None
) -> OperationContext:
    return OperationContext(
        operation_id="op-" + uuid4().hex,
        run_id=binding.run.owner.run_id,
        owner_id=binding.run.owner.owner_id,
        attempt_id=attempt,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )


class UnitClaimAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.create_calls = 0
        self.read_calls = 0

    def authorize_create(
        self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
    ) -> None:
        self.create_calls += 1
        if self.denied or binding.task not in plan.tasks or op.run_id != plan.run_id:
            raise OwnershipConflict("unit claim admission denied")

    def verify_owner(self, record: SourceClaimRecord, op: OperationContext) -> None:
        self.read_calls += 1
        if self.denied or op.owner_id != record.binding.run.owner.owner_id:
            raise OwnershipConflict("unit claim caller denied")


@dataclass
class Fixture:
    root: Path
    store: FileEvidenceStore
    plans: EvidenceRunPlans
    controls: OperationGuards
    cancel: CancelSwitch
    authority: UnitClaimAuthority
    binding: SourceClaimBinding

    def ledger(self, store: EvidenceStore | None = None) -> FileSourceClaims:
        return FileSourceClaims(
            self.root / "claims",
            "unit-scope",
            self.controls,
            store or self.store,
            self.plans,
            self.authority,
        )

    def attempt(self, ref: object) -> AttemptBinding:
        return AttemptBinding.model_validate(
            dict(
                run=self.binding.run,
                attempt_id="attempt",
                task=self.binding.task.identity,
                claim_ref=ref,
            )
        )

    @property
    def path(self) -> Path:
        return self.root / "claims" / self.binding.key.filename


def fixture(root: Path) -> Fixture:
    (root / "evidence").mkdir()
    (root / "claims").mkdir()
    store = FileEvidenceStore(root / "evidence")
    cancel = CancelSwitch()
    controls = OperationGuards(SystemClock(), cancel)
    plans = EvidenceRunPlans(store, controls)
    plan = persisted_plan(store)
    run = plan_binding(plan)
    tentative = SourceClaimBinding(scope_id="unit-scope", run=run, task=plan.tasks[0])
    ref = plans.publish(plan, operation(tentative))
    run = RunBinding.model_validate(run.model_copy(update={"plan_ref": ref}))
    return Fixture(
        root,
        store,
        plans,
        controls,
        cancel,
        UnitClaimAuthority(),
        SourceClaimBinding(scope_id="unit-scope", run=run, task=plan.tasks[0]),
    )
