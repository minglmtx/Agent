"""Same-call complete claim bytes; durable ledger and current gates stay live."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.execution_task_source import ClaimedExecutionSourceFacts
from lab_generate_skill.domain.lifecycle import CancellationRef
from claim_fixtures import fixture, operation
from execution_task_phase_fixtures import phase_case


def test_verified_claim_reads_live_ledger_without_duplicate_cas_and_rejects_revocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fixture(tmp_path)
    ledger = f.ledger()
    receipt = ledger.claim(f.binding, operation(f.binding))
    before = f.path.read_bytes()

    def no_cas(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Verified same-call claim body was fetched again")

    monkeypatch.setattr(ledger._evidence, "load", no_cas)
    for _ in range(2):
        assert (
            ledger.require_source_verified(
                receipt, f.binding.run, f.binding.task, operation(f.binding)
            )
            == receipt.record
        )
    assert f.authority.read_calls == 2
    f.authority.denied = True
    with pytest.raises(OwnershipConflict, match="caller denied"):
        ledger.require_source_verified(
            receipt, f.binding.run, f.binding.task, operation(f.binding)
        )
    assert f.path.read_bytes() == before


@pytest.mark.parametrize(
    "fault",
    ["wrong-body", "wrong-task", "missing-ledger", "cancelled", "ledger-mismatch"],
)
def test_claim_body_never_bypasses_binding_missing_ledger_or_cancel(
    tmp_path: Path, fault: str
) -> None:
    f = fixture(tmp_path)
    ledger = f.ledger()
    receipt = ledger.claim(f.binding, operation(f.binding))
    task = f.binding.task
    op = operation(f.binding)
    expected: type[Exception]
    if fault == "wrong-body":
        receipt = receipt.model_copy(
            update={
                "reference": receipt.reference.model_copy(update={"sha256": "0" * 64})
            }
        )
        expected = ValidationError
    elif fault == "wrong-task":
        task = task.model_copy(update={"registration_id": "other-task"})
        expected = OwnershipConflict
    elif fault == "missing-ledger":
        f.path.unlink()
        expected = EvidenceIntegrityError
    elif fault == "ledger-mismatch":
        changed = receipt.record.model_copy(update={"operation": operation(f.binding)})
        ref = f.store.put(
            changed.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="source-claim/1",
                visibility="private",
                producer="source-claims-v1",
            ),
            control=f.controls.bind(op),
        )
        receipt = SourceClaimReceipt(record=changed, reference=ref)
        expected = EvidenceIntegrityError
    else:
        op = op.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="claim-cancel", run_id=op.run_id, owner_id=op.owner_id
                )
            }
        )
        f.cancel.cancelled = True
        expected = OperationStopped
    with pytest.raises(expected):
        ledger.require_source_verified(receipt, f.binding.run, task, op)
    if fault == "missing-ledger":
        assert not f.path.exists()


def test_source_load_and_recheck_consume_claim_proof_but_reject_current_store_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = phase_case(tmp_path / "source").task
    original = c.source.source_reader
    op = c.plan.read_operation
    control = c.deps.controls.bind(op)
    facts = original.load(c.plan, op, control)
    source = facts.source
    record = original.claims.require_source(
        source.intent.binding.claim_ref, source.run, source.task, op
    )
    claimed = ClaimedExecutionSourceFacts(
        **vars(facts),
        claim=SourceClaimReceipt(
            record=record, reference=source.intent.binding.claim_ref
        ),
    )

    class CurrentChecks:
        denied = False
        calls = 0

        def load_source(
            self, plan: Any, operation: Any, control: Any
        ) -> ClaimedExecutionSourceFacts:
            self.verify_current(plan, claimed, operation, control)
            return claimed

        def verify_current(
            self, plan: Any, facts: Any, operation: Any, control: Any
        ) -> None:
            self.calls += 1
            control.checkpoint()
            if self.denied:
                raise InvalidTransition("Original storage quarantined")

    checks = CurrentChecks()
    reader = OriginalExecutionTaskSource(
        original.plans,
        original.claims,
        original.contexts,
        original.bindings,
        original.reads.store,
        source_checks=checks,
    )

    def no_cas(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Source consumer repeated claim CAS after full installed proof")

    monkeypatch.setattr(original.claims, "require_source", no_cas)
    assert reader.load(c.plan, op, control) == claimed
    reader.recheck(c.plan, claimed, op, control)
    checks.denied = True
    with pytest.raises(InvalidTransition, match="quarantined"):
        reader.recheck(c.plan, claimed, op, control)
    checks.denied = False
    c.source.claim_authority.denied = True
    with pytest.raises(OwnershipConflict):
        reader.recheck(c.plan, claimed, op, control)
    assert checks.calls == 4
