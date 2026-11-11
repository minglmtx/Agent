"""Resource-specific recovery remains independently checked, with one body read."""

from collections import Counter
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from retrieval_fixtures import reference
from state_storage_fixtures import fixture


@pytest.mark.parametrize(
    "fault", ["normal", "missing", "corrupt", "owner", "attempt", "protected"]
)
def test_extra_original_resource_recovery_is_read_once_and_keeps_its_full_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = fixture(tmp_path)
    old = c.reset_inputs
    extra = old.task_recovery.model_copy(
        update={"recovery_id": "separate-original-browser-recovery"}
    )
    if fault == "owner":
        extra = extra.model_copy(
            update={
                "owner": extra.owner.model_copy(update={"owner_id": "foreign-owner"})
            }
        )
    elif fault == "attempt":
        extra = extra.model_copy(update={"attempt_id": "foreign-attempt"})
    protected = reference({"only_extra_recovery_protection": True}, store=c.store)
    extra = extra.model_copy(
        update={"protected_state": (*extra.protected_state, protected)}
    )
    extra_ref = reference(extra, "recovery-plan/1", store=c.store)
    first = old.closures[0]
    token = first.token.model_copy(update={"recovery_ref": extra_ref})
    closure = first.model_copy(update={"token": token})
    closure_ref = reference(closure, "closure-receipt/1", store=c.store)
    plan = old.plan.model_copy(
        update={"attempt_allocations": (token, *old.plan.attempt_allocations[1:])}
    )
    plan_ref = reference(plan, "reset-plan/1", store=c.store)
    closures = (closure, *old.closures[1:])
    closure_refs = (closure_ref, *old.closure_refs[1:])
    task = old.task.model_copy(update={"after_closure_refs": closure_refs})
    task_ref = reference(task, "task-reset/1", store=c.store)
    environment = old.environment.model_copy(update={"after_task_reset_ref": task_ref})
    environment_ref = reference(environment, "environment-reset/1", store=c.store)
    health = old.health.model_copy(
        update={"after_environment_reset_ref": environment_ref}
    )
    health_ref = reference(health, "reset-health/1", store=c.store)
    inputs = old.model_copy(
        update=dict(
            plan=plan,
            plan_ref=plan_ref,
            closures=closures,
            closure_refs=closure_refs,
            task=task,
            task_ref=task_ref,
            environment=environment,
            environment_ref=environment_ref,
            health=health,
            health_ref=health_ref,
        )
    )
    receipt = assemble_reset(inputs, c.reset.operation)
    if fault == "missing":
        (tmp_path / "blobs" / extra_ref.sha256).unlink()
    elif fault == "corrupt":
        (tmp_path / "blobs" / extra_ref.sha256).write_bytes(b"corrupt extra recovery")
    elif fault == "protected":
        (tmp_path / "blobs" / protected.sha256).unlink()
    counts: Counter[EvidenceRef] = Counter()
    read = c.store.read

    def counted(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        counts[ref] += 1
        return read(ref, control=control)

    monkeypatch.setattr(c.store, "read", counted)
    before = set((tmp_path / "blobs").iterdir())
    if fault != "normal":
        error = (
            EvidenceNotFound
            if fault in ("missing", "protected")
            else EvidenceIntegrityError if fault == "corrupt" else OwnershipConflict
        )
        with pytest.raises(error):
            c.adapter.publish_reset_inputs(receipt, inputs, receipt.operation)
        assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls
    else:
        result = c.adapter.publish_reset_inputs(receipt, inputs, receipt.operation)
        assert (
            counts[extra_ref] == 1
            and counts[protected] == 1
            and all(n == 1 for n in counts.values())
        )
        assert c.adapter.load_reset_publication(result, receipt.operation) == receipt
        assert counts[extra_ref] == 1
