"""Actual CAS graphs with explicit unit-only source/comparison authority."""

from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
import context_contract_fixtures as contexts
import state_contract_fixtures as states
from retrieval_fixtures import reference
from state_storage_fixtures import UnitStateAuthority
from test_run_journal import CancelSwitch, command


class UnitContextAuthority(UnitStateAuthority):
    def __init__(self) -> None:
        super().__init__()
        self.denied_context = False
        self.denied_equivalence = False
        self.context_operations: list[OperationContext] = []

    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None:
        self.calls.append("context")
        self.context_operations.append(op)
        if self.denied_context:
            raise OwnershipConflict("Unit source permission denied")

    def verify_equivalence(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
    ) -> None:
        self.calls.append("equivalence")
        if self.denied_equivalence:
            raise OwnershipConflict("Unit comparison permission denied")


@dataclass
class ContextStorageFixture:
    store: FileEvidenceStore
    adapter: EvidenceContextRecords
    authority: UnitContextAuthority
    switch: CancelSwitch
    inputs: EquivalenceInputs
    comparison: EquivalenceReceipt
    protected_ref: EvidenceRef

    def candidate(self, kind: str) -> PublicContextReceipt | EquivalenceReceipt:
        return self.inputs.source if kind == "context" else self.comparison

    def publish(
        self, receipt: PublicContextReceipt | EquivalenceReceipt, op: OperationContext
    ) -> EvidenceRef:
        if isinstance(receipt, PublicContextReceipt):
            return self.adapter.publish_context(receipt, op)
        return self.adapter.publish_equivalence(receipt, op)

    def load(
        self, kind: str, ref: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt | EquivalenceReceipt:
        if kind == "context":
            return self.adapter.load_context(ref, op)
        return self.adapter.load_equivalence(ref, op)


def fixture(
    root: Path, *, allowed_actions: tuple[str, ...] = ("stop",)
) -> ContextStorageFixture:
    store = FileEvidenceStore(root)
    protected = reference({"protected": "context-unit"}, store=store)
    original_recovery = states.recovery

    def stored(
        value: object, schema: str = "fixture/1", visibility: str = "private"
    ) -> EvidenceRef:
        return reference(value, schema, visibility, store)

    def recovery(attempt: bool) -> RecoveryPlan:
        return original_recovery(attempt).model_copy(
            update={"protected_state": (protected,)}
        )

    with pytest.MonkeyPatch.context() as patch:
        for module in (states, contexts):
            patch.setattr(module, "reference", stored)
            patch.setattr(module, "recovery", recovery)
        inputs = contexts.equivalence_inputs(allowed_actions=allowed_actions)
    comparison = assemble_equivalence(
        inputs, command("equivalence", attempt="candidate")
    )
    authority = UnitContextAuthority()
    switch = CancelSwitch()
    adapter = EvidenceContextRecords(
        store, OperationGuards(SystemClock(), switch), authority
    )
    return ContextStorageFixture(
        store, adapter, authority, switch, inputs, comparison, protected
    )
