"""Real claims/CAS/journals; failures stop new work, not original fact recovery."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.admit_candidate import prepare_actor_input
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.construction import CallPlanned, ConstructionPlan
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from actor_admission_fixtures import fixture as actor_fixture
from construction_storage_fixtures import fixture
from test_construction_journal import snapshot_path
from test_run_journal import command


@pytest.mark.parametrize("stage", ["create", "generator", "attempt", "teacher"])
def test_each_new_work_gate_checks_original_claim(tmp_path: Path, stage: str) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    if stage == "create":
        data.claim_authority.denied = True
        with pytest.raises(OwnershipConflict, match="unit claim caller denied"):
            journal.create(data.plan, command())
        assert not snapshot_path(data).exists()
        return
    progress = journal.create(data.plan, command())
    wanted = {"generator": "generate", "attempt": "execute", "teacher": "revise"}[stage]
    for _ in range(40):
        if progress.project().next_action.kind == wanted:
            break
        event = data.event(progress)
        progress = journal.append(event, progress.revision, event.operation)
    assert progress.project().next_action.kind == wanted
    event = data.event(progress)
    before = snapshot_path(data).read_bytes()
    data.claim_authority.denied = True
    with pytest.raises(OwnershipConflict, match="unit claim caller denied"):
        journal.append(event, progress.revision, event.operation)
    assert snapshot_path(data).read_bytes() == before


def test_revoked_claim_keeps_read_replay_and_observed_result_exit(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    initial = journal.create(data.plan, creation)
    event = data.event(initial)
    assert isinstance(event, CallPlanned)
    progress = journal.append(event, initial.revision, event.operation)
    result = data.event(progress)
    data.claim_authority.denied = True
    assert journal.read(command()) == progress
    assert journal.create(data.plan, creation) == progress
    assert journal.append(event, initial.revision, event.operation) == progress
    closed = journal.append(result, progress.revision, result.operation)
    assert closed.project().next_action.kind == "generate"
    assert journal.append(result, progress.revision, result.operation) == closed
    next_event = data.event(closed)
    with pytest.raises(OwnershipConflict):
        journal.append(next_event, closed.revision, next_event.operation)
    assert journal.read(command()) == closed


@pytest.mark.parametrize("fault", ["denied", "missing", "corrupt"])
def test_actor_gate_checks_durable_original_claim(tmp_path: Path, fault: str) -> None:
    data = actor_fixture(tmp_path)
    record = SourceClaimRecord.model_validate_json(
        data.data.store.read(data.data.plan.claim_ref)
    )
    path = tmp_path / "claims" / record.binding.key.filename
    before = data.harness.path.read_bytes()
    construction = data.deps.construction.read(data.request.read_operation)
    if fault == "denied":
        data.data.claim_authority.denied = True
        expected: type[Exception] = OwnershipConflict
    else:
        if fault == "missing":
            path.unlink()
        else:
            path.write_bytes(b"{}")
        expected = EvidenceIntegrityError
    with pytest.raises(expected):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0
    assert data.harness.path.read_bytes() == before
    assert data.deps.construction.read(data.request.read_operation) == construction


@pytest.mark.parametrize("consumer", ["construction", "actor"])
@pytest.mark.parametrize("bad", [None, {}, "", 1])
def test_consumers_revalidate_invalid_port_results(
    tmp_path: Path, consumer: str, bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    if consumer == "construction":
        data = fixture(tmp_path)
        journal = data.journal()
        monkeypatch.setattr(
            journal.verifier.claims, "require_source", lambda *args: bad
        )
        with pytest.raises(ValidationError):
            journal.create(data.plan, command())
        assert not snapshot_path(data).exists()
    else:
        actor = actor_fixture(tmp_path)
        monkeypatch.setattr(actor.deps.claims, "require", lambda *args: bad)
        with pytest.raises(ValidationError):
            prepare_actor_input(actor.request, actor.deps)
        assert actor.authority.calls == 0


def test_actor_checks_full_private_task_after_attempt_identity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = actor_fixture(tmp_path)
    record = SourceClaimRecord.model_validate_json(
        data.data.store.read(data.data.plan.claim_ref)
    )
    other_task = record.binding.task.model_copy(
        update={"private_spec_ref": record.binding.task.baseline_ref}
    )
    assert other_task != record.binding.task
    changed = record.model_copy(
        update={"binding": record.binding.model_copy(update={"task": other_task})}
    )
    monkeypatch.setattr(data.deps.claims, "require", lambda *args: changed)
    with pytest.raises(ValueError, match="exact original record"):
        prepare_actor_input(data.request, data.deps)
    assert data.authority.calls == 0


@pytest.mark.parametrize("version", ["construction-plan/1", "construction-plan/2"])
def test_old_plan_formats_are_not_silently_upgraded(
    tmp_path: Path, version: str
) -> None:
    data = fixture(tmp_path)
    with pytest.raises(ValidationError):
        ConstructionPlan.model_validate(
            data.plan.model_copy(update={"schema_version": version})
        )
    assert not snapshot_path(data).exists()
