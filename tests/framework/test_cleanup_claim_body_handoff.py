"""Original cleanup claim body replaces CAS rereads, never live ledger checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from claim_fixtures import fixture, operation
from execution_task_phase_fixtures import phase_case
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.execution_task_source import ClaimedExecutionSourceFacts
from lab_generate_skill.domain.lifecycle import CancellationRef


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "body",
        "reference",
        "attempt",
        "task",
        "run",
        "missing",
        "corrupt",
        "changed-ledger",
        "revoked",
        "deadline",
        "cancelled",
    ],
)
def test_actual_attempt_claim_body_keeps_exact_binding_and_live_ledger_without_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = fixture(tmp_path)
    ledger = f.ledger()
    receipt = ledger.claim(f.binding, operation(f.binding))
    before = f.path.read_bytes()
    attempt = f.attempt(receipt.reference)
    op = operation(f.binding, attempt="attempt")
    expected: type[Exception] = OwnershipConflict
    if fault == "body":
        receipt = receipt.model_copy(
            update={
                "reference": receipt.reference.model_copy(update={"sha256": "0" * 64})
            }
        )
        expected = ValidationError
    elif fault == "reference":
        attempt = attempt.model_copy(
            update={
                "claim_ref": attempt.claim_ref.model_copy(update={"sha256": "0" * 64})
            }
        )
    elif fault == "attempt":
        op = op.model_copy(update={"attempt_id": "other"})
    elif fault == "task":
        attempt = attempt.model_copy(
            update={"task": attempt.task.model_copy(update={"task_id": "other"})}
        )
    elif fault == "run":
        attempt = attempt.model_copy(
            update={"run": attempt.run.model_copy(update={"submission_key": "other"})}
        )
    elif fault == "missing":
        f.path.unlink()
        expected = EvidenceIntegrityError
    elif fault == "corrupt":
        f.path.write_bytes(b"{")
        expected = EvidenceIntegrityError
    elif fault == "changed-ledger":
        changed = receipt.record.model_copy(update={"operation": operation(f.binding)})
        f.path.write_bytes(changed.model_dump_json().encode())
        expected = EvidenceIntegrityError
    elif fault == "revoked":
        f.authority.denied = True
    elif fault == "deadline":
        op = op.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        expected = OperationStopped
    elif fault == "cancelled":
        op = op.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="unit-cancel", run_id=op.run_id, owner_id=op.owner_id
                )
            }
        )
        f.cancel.cancelled = True
        expected = OperationStopped

    def forbidden_load(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Claim body was already supplied by the same complete source proof")

    monkeypatch.setattr(ledger._evidence, "load", forbidden_load)
    if fault == "none":
        for _ in range(2):
            assert ledger.require_verified(receipt, attempt, op) == receipt.record
        assert f.authority.read_calls == 2
        f.authority.denied = True
        with pytest.raises(OwnershipConflict):
            ledger.require_verified(receipt, attempt, op)
        assert f.path.read_bytes() == before
    else:
        with pytest.raises(expected):
            ledger.require_verified(receipt, attempt, op)
        if fault == "missing":
            assert not f.path.exists()
        elif fault not in {"corrupt", "changed-ledger"}:
            assert f.path.read_bytes() == before


def claimed_sources(tmp_path: Path) -> Any:
    f = phase_case(tmp_path / "source")
    c = f.task
    original = c.source.source_reader
    op = c.plan.read_operation
    control = c.deps.controls.bind(op)
    facts = original.load(c.plan, op, control)
    record = original.claims.require_source(
        facts.source.intent.binding.claim_ref, facts.source.run, facts.source.task, op
    )
    claimed = ClaimedExecutionSourceFacts(
        **vars(facts),
        claim=SourceClaimReceipt(
            record=record, reference=facts.source.intent.binding.claim_ref
        ),
    )

    class FrozenSourceChecks:
        def load_source(
            self, plan: Any, operation: Any, control: Any
        ) -> ClaimedExecutionSourceFacts:
            self.verify_current(plan, claimed, operation, control)
            return claimed

        def verify_current(
            self, plan: Any, facts: Any, operation: Any, control: Any
        ) -> None:
            control.checkpoint()
            assert facts == claimed and plan.intent == claimed.source.intent

    # Only the external source-proof edge is an isolated engineering premise.
    # Actual OriginalExecutionTaskSource, FileSourceClaims and both finalization
    # gates still execute and check their current durable ownership.
    f.sources.source = OriginalExecutionTaskSource(
        original.plans,
        original.claims,
        original.contexts,
        original.bindings,
        original.reads.store,
        source_checks=FrozenSourceChecks(),
    )
    return f


@pytest.mark.parametrize("revoke_at_return", [False, True])
def test_actual_shared_cleanup_consumes_source_body_and_rechecks_original_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revoke_at_return: bool
) -> None:
    f = claimed_sources(tmp_path)
    c = f.task
    inside_cleanup = False
    checks = 0
    verify = f.finalization.verify
    require = c.deps.claims.require_verified
    load = c.deps.claims._evidence.load
    source_verify = f.cleanup_source.verify

    def check(*args: Any, **kwargs: Any) -> Any:
        nonlocal checks
        checks += 1
        return require(*args, **kwargs)

    def read(*args: Any, **kwargs: Any) -> Any:
        if inside_cleanup:
            pytest.fail(
                "Cleanup fetched claim CAS despite its still-open original source proof"
            )
        return load(*args, **kwargs)

    def gate(*args: Any, **kwargs: Any) -> Any:
        nonlocal inside_cleanup
        inside_cleanup = True
        try:
            return verify(*args, **kwargs)
        finally:
            inside_cleanup = False

    def source_gate(*args: Any, **kwargs: Any) -> None:
        source_verify(*args, **kwargs)
        if revoke_at_return:
            c.source.claim_authority.denied = True

    monkeypatch.setattr(c.deps.claims, "require_verified", check)
    monkeypatch.setattr(c.deps.claims._evidence, "load", read)
    monkeypatch.setattr(f.finalization, "verify", gate)
    monkeypatch.setattr(f.cleanup_source, "verify", source_gate)
    if revoke_at_return:
        with pytest.raises(TaskExecutionUnconfirmed):
            execute_task(c.plan, c.deps)
        assert checks == 2 and "restore" not in c.phases.calls
    else:
        assert execute_task(c.plan, c.deps).evaluation.status == "failure"
        assert checks == 4 and len(f.cleanup_source.calls) == 2
        assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


def test_claim_body_cannot_escape_its_original_source_read_thread_or_lifetime(
    tmp_path: Path,
) -> None:
    f = claimed_sources(tmp_path)
    c = f.task
    op = c.plan.read_operation
    opened = f.sources.open_run_read(c.plan, op, c.deps.controls.bind(op))
    assert opened.claim is not None
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(lambda: opened.claim).result()
    opened.close()
    with pytest.raises(OwnershipConflict):
        _ = opened.claim
