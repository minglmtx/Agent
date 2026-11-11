"""Real CAS state graphs with explicitly unit-only historical authority."""

from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    assemble_baseline,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt, assemble_reset
from lab_generate_skill.runtime.lifecycle import OperationGuards
import state_contract_fixtures as contracts
from retrieval_fixtures import reference
from test_run_journal import CancelSwitch


class UnitStateAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls: list[str] = []

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        self.calls.append("baseline")
        if self.denied or inputs.spec.spec_id != "initial":
            raise OwnershipConflict("Unit baseline authority rejected")

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        self.calls.append("reset")
        if self.denied or inputs.spec.spec_id != "initial":
            raise OwnershipConflict("Unit reset authority rejected")


@dataclass
class StateStorageFixture:
    store: FileEvidenceStore
    adapter: EvidenceStateRecords
    authority: UnitStateAuthority
    switch: CancelSwitch
    baseline_inputs: BaselineInputs
    reset_inputs: ResetInputs
    baseline: BaselineReceipt
    reset: ResetReceipt
    protected_ref: EvidenceRef

    def candidate(self, kind: str) -> BaselineReceipt | ResetReceipt:
        return self.baseline if kind == "baseline" else self.reset

    def publish(
        self, receipt: BaselineReceipt | ResetReceipt, op: OperationContext
    ) -> EvidenceRef:
        if isinstance(receipt, BaselineReceipt):
            return self.adapter.publish_baseline(receipt, op)
        return self.adapter.publish_reset(receipt, op)

    def load(
        self, kind: str, ref: EvidenceRef, op: OperationContext
    ) -> BaselineReceipt | ResetReceipt:
        if kind == "baseline":
            return self.adapter.load_baseline(ref, op)
        return self.adapter.load_reset(ref, op)


def fixture(root: Path) -> StateStorageFixture:
    store = FileEvidenceStore(root)
    protected = reference({"protected": "unit"}, store=store)
    original_recovery = contracts.recovery

    def stored(
        value: object, schema: str = "fixture/1", visibility: str = "private"
    ) -> EvidenceRef:
        return reference(value, schema, visibility, store)

    def recovery(attempt: bool) -> RecoveryPlan:
        return original_recovery(attempt).model_copy(
            update={"protected_state": (protected,)}
        )

    # All reference creation in the pure graph fixture now persists real bytes.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(contracts, "reference", stored)
        patch.setattr(contracts, "recovery", recovery)
        baseline = contracts.baseline_inputs()
        reset = contracts.reset_inputs()
    authority = UnitStateAuthority()
    switch = CancelSwitch()
    adapter = EvidenceStateRecords(
        store, OperationGuards(SystemClock(), switch), authority
    )
    return StateStorageFixture(
        store,
        adapter,
        authority,
        switch,
        baseline,
        reset,
        assemble_baseline(baseline, contracts.op("baseline-summary")),
        assemble_reset(reset, contracts.op("reset-summary", cleanup=True)),
        protected,
    )
