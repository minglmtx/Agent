"""Real qualification consumer; new work differs from diagnostic replay."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.domain.construction import (
    AttemptPlanned,
    CallCompleted,
    CallPlanned,
    ConstructionPlan,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import EvidenceNotFound, OwnershipConflict
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.reset import ResetReceipt
from lab_generate_skill.domain.run_plan import RunPlan
from construction_storage_fixtures import fixture, put
from test_construction_journal import snapshot_path
from test_run_journal import command


def test_creation_consumes_actual_source_and_its_full_private_task(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    receipt = PublicContextReceipt.model_validate_json(
        data.store.read(data.plan.context_receipt_ref)
    )
    assert receipt.public_context_ref == data.plan.public_context_ref
    assert receipt.spec_ref == data.plan.task.baseline_ref
    data.context_authority.calls.clear()
    progress = data.journal().create(data.plan, command())
    assert progress.plan == data.plan
    assert data.context_authority.calls == ["baseline", "reset", "context"]


@pytest.mark.parametrize("stage", ["create", "call", "attempt"])
@pytest.mark.parametrize("fault", ["missing_closure", "authority"])
def test_new_work_rechecks_source_and_preserves_journal_on_failure(
    tmp_path: Path, stage: str, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    event = None
    if stage != "create":
        progress = journal.create(data.plan, command())
        event = data.event(progress)
        if stage == "attempt":
            while not isinstance(event, AttemptPlanned):
                progress = journal.append(event, progress.revision, event.operation)
                event = data.event(progress)
        else:
            assert isinstance(event, CallPlanned)
    path = snapshot_path(data)
    before = path.read_bytes() if path.exists() else None
    expected: type[Exception]
    if fault == "authority":
        data.context_authority.denied_context = True
        expected = OwnershipConflict
    else:
        source = PublicContextReceipt.model_validate_json(
            data.store.read(data.plan.context_receipt_ref)
        )
        reset = ResetReceipt.model_validate_json(data.store.read(source.reset_ref))
        (tmp_path / "evidence" / "blobs" / reset.closure_refs[0].sha256).unlink()
        expected = EvidenceNotFound
    with pytest.raises(expected):
        if stage == "create":
            journal.create(data.plan, command())
        else:
            assert event is not None
            journal.append(event, progress.revision, event.operation)
    if before is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == before
        assert journal.read(command()) == progress


@pytest.mark.parametrize("field", ["private_spec_ref", "registration_id"])
def test_same_task_id_with_different_private_binding_is_rejected(
    tmp_path: Path, field: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    plans = EvidenceRunPlans(data.store, journal.controls)
    run = plans.load(data.plan.run, command())
    value = (
        put(data.store, {"other": True})
        if field == "private_spec_ref"
        else "different-registration"
    )
    task = run.tasks[0].model_copy(update={field: value})
    changed = RunPlan.model_validate(run.model_copy(update={"tasks": (task,)}))
    run_ref = plans.publish(changed, command())
    plan = ConstructionPlan.from_run_plan(
        changed,
        data.plan.run.model_copy(update={"plan_ref": run_ref}),
        task.identity.task_id,
        claim_ref=data.plan.claim_ref,
        public_context_ref=data.plan.public_context_ref,
        context_receipt_ref=data.plan.context_receipt_ref,
        retrieval_ref=data.plan.retrieval_ref,
        retrieval_scope=data.plan.retrieval_scope,
    )
    with pytest.raises(OwnershipConflict, match="complete run or task"):
        data.journal(plan=plan).create(plan, command())
    # The earlier claim gate must not make the context check untested.
    op = command()
    with pytest.raises(OwnershipConflict, match="private task binding"):
        journal.verifier._qualified_context(plan, op, journal.controls.bind(op))
    assert not snapshot_path(data).exists()


def test_old_unit_qualification_is_not_a_supported_fallback(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    legacy = put(
        data.store,
        {"unit_qualified": True, "context": data.plan.public_context_ref.sha256},
        "public-context-receipt/1",
    )
    plan = data.plan.model_copy(update={"context_receipt_ref": legacy})
    with pytest.raises(ValidationError):
        data.journal(plan=plan).create(plan, command())
    assert not snapshot_path(data).exists()


def test_exact_public_reference_is_required_even_for_equal_bytes(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    public = PublicConstructionContext.model_validate_json(
        data.store.read(data.plan.public_context_ref)
    )
    other_reference = put(data.store, public, public.schema_version, "public")
    assert other_reference.sha256 == data.plan.public_context_ref.sha256
    assert (
        other_reference != data.plan.public_context_ref
    )  # Different producer metadata.
    plan = data.plan.model_copy(update={"public_context_ref": other_reference})
    with pytest.raises(OwnershipConflict, match="Qualified source"):
        data.journal(plan=plan).create(plan, command())


def test_denied_source_allows_diagnostics_and_known_response_but_not_new_call(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    progress = journal.create(data.plan, creation)
    planned = data.event(progress)
    assert isinstance(planned, CallPlanned)
    progress = journal.append(planned, progress.revision, planned.operation)
    data.context_authority.denied_context = True
    assert journal.read(command()) == progress
    assert journal.create(data.plan, creation) == progress
    assert journal.append(planned, -1, planned.operation) == progress
    completed = data.event(progress)
    assert isinstance(completed, CallCompleted)
    progress = journal.append(completed, progress.revision, completed.operation)
    # Frozen method generates all four candidates before executing attempts.
    next_call = data.event(progress)
    assert isinstance(next_call, CallPlanned)
    before = snapshot_path(data).read_bytes()
    with pytest.raises(OwnershipConflict):
        journal.append(next_call, progress.revision, next_call.operation)
    assert snapshot_path(data).read_bytes() == before
