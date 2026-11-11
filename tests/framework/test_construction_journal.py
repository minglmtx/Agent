"""Stored construction contracts: real CAS bytes, explicit unit authority only."""

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter, ValidationError

from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    AttemptResolved,
    CallCompleted,
    CallPlanned,
    CallUncertain,
    ConstructionPlan,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_inputs import (
    GenerationInput,
    PublicConstructionContext,
)
from lab_generate_skill.domain.construction_journal import (
    ConstructionCommitUnconfirmed,
    ConstructionSnapshot,
)
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    append_construction_event,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evaluation import CheckResult, Evaluation

from construction_storage_fixtures import fixture, limits, put, StorageFixture
from test_run_journal import command


def snapshot_path(data: StorageFixture) -> Path:
    journal = data.journal()
    return data.root / "journal" / journal.file.name


@pytest.mark.parametrize(
    "status,count,selection", [("success", 5, "accepted"), ("failure", 7, "rejected")]
)
def test_complete_stored_flow_matches_pure_history(
    tmp_path: Path, status: str, count: int, selection: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    progress = journal.create(data.plan, creation)
    expected = progress
    while progress.project().next_action.kind != "complete":
        event = data.event(progress, status=status)
        expected = append_construction_event(expected, event, expected.revision)
        progress = data.journal().append(event, progress.revision, event.operation)
        assert progress == expected == data.journal().read(command())
    view = progress.project()
    assert len(view.attempts) == count
    assert view.selection is not None and view.selection.status == selection
    assert journal.create(data.plan, creation) == progress
    assert (
        ConstructionSnapshot.model_validate_json(
            snapshot_path(data).read_bytes()
        ).progress
        == progress
    )


def test_replay_is_exact_and_not_a_new_permission(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    progress = journal.create(data.plan, creation)
    event = data.event(progress)
    saved = journal.append(event, -1, event.operation)
    before = snapshot_path(data).read_bytes()
    data.authority.denied = True
    assert data.journal().append(event, -1, event.operation) == saved
    assert data.journal().read(command()) == saved
    assert data.journal().create(data.plan, creation) == saved
    other = data.event(saved)
    with pytest.raises(OwnershipConflict):
        journal.append(other, saved.revision, other.operation)
    with pytest.raises(OwnershipConflict):
        journal.create(data.plan, command())
    assert snapshot_path(data).read_bytes() == before


@pytest.mark.parametrize("bad", [None, [], {}, {"kind": "invalid"}])
def test_invalid_payload_before_any_files(tmp_path: Path, bad: object) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    with pytest.raises(ValidationError):
        journal.append(cast(ProgressEvent, bad), -1, command())
    assert list((tmp_path / "journal").iterdir()) == []


@pytest.mark.parametrize("bad", [True, False, 1.0, "0", None, -2])
def test_invalid_revision_before_any_files(tmp_path: Path, bad: object) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    event = data.event(ConstructionProgress(plan=data.plan))
    with pytest.raises(ValueError):
        journal.append(event, cast(int, bad), event.operation)
    assert list((tmp_path / "journal").iterdir()) == []


def test_operation_scope_and_identity(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    progress = journal.create(data.plan, creation)
    event = data.event(progress)
    before = snapshot_path(data).read_bytes()
    with pytest.raises(OwnershipConflict):
        journal.append(event, -1, command())
    reused = event.model_copy(update={"operation": creation})
    with pytest.raises(OwnershipConflict):
        journal.append(reused, -1, creation)
    with pytest.raises(OwnershipConflict):
        journal.read(command(attempt="different"))
    with pytest.raises(OwnershipConflict):
        journal.read(command().model_copy(update={"owner_id": "other"}))
    assert snapshot_path(data).read_bytes() == before


def test_missing_and_stale_history(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    initial = ConstructionProgress(plan=data.plan)
    event = data.event(initial)
    with pytest.raises(EvidenceNotFound):
        journal.read(command())
    with pytest.raises(EvidenceNotFound):
        journal.append(event, -1, event.operation)
    assert not snapshot_path(data).exists()
    journal.create(data.plan, command())
    saved = journal.append(event, -1, event.operation)
    other = data.event(saved)
    before = snapshot_path(data).read_bytes()
    with pytest.raises(RevisionConflict):
        journal.append(other, -1, other.operation)
    assert snapshot_path(data).read_bytes() == before


def test_numeric_equality_cannot_bypass_replay_validation(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    journal.append(event, -1, event.operation)
    malformed = event.model_copy(
        update={"call": event.call.model_copy(update={"seed": float(event.call.seed)})}
    )
    assert malformed == event
    with pytest.raises(ValidationError):
        journal.append(malformed, -1, event.operation)


@pytest.mark.parametrize(
    "change", ["claim", "context", "qualified", "retrieval", "method"]
)
def test_creation_checks_frozen_content_and_authority(
    tmp_path: Path, change: str
) -> None:
    data = fixture(tmp_path)
    plan = data.plan
    if change == "claim":
        plan = plan.model_copy(
            update={
                "claim_ref": put(data.store, {"unit_claim": False}, "source-claim/1")
            }
        )
    elif change == "context":
        context = PublicConstructionContext.model_validate_json(
            data.store.read(plan.public_context_ref)
        )
        context = context.model_copy(
            update={
                "task": context.task.model_copy(
                    update={"goal": "different public task"}
                )
            }
        )
        plan = plan.model_copy(
            update={
                "public_context_ref": put(
                    data.store, context, "public-construction-context/1", "public"
                )
            }
        )
    elif change == "qualified":
        plan = plan.model_copy(
            update={
                "context_receipt_ref": put(data.store, {}, "public-context-receipt/1")
            }
        )
    elif change == "retrieval":
        plan = plan.model_copy(
            update={
                "retrieval_ref": put(
                    data.store,
                    {"context": "wrong", "split": "train"},
                    "retrieval-result/1",
                )
            }
        )
    else:
        plan = plan.model_copy(
            update={"method": plan.method.model_copy(update={"seed": 43})}
        )
    plan = ConstructionPlan.model_validate(plan)
    # Old placeholder claim/qualification/retrieval JSON is now a schema error, not a unit
    # authority verdict; every other case remains an ownership conflict.
    expected_error = (
        ValidationError
        if change in ("claim", "qualified", "retrieval")
        else OwnershipConflict
    )
    with pytest.raises(expected_error):
        data.journal(plan=plan).create(plan, command())
    assert not snapshot_path(data).exists()


@pytest.mark.parametrize(
    "change", ["seed", "context", "skills", "parameters", "missing", "invalid_json"]
)
def test_actual_generator_input_not_just_reference_shape(
    tmp_path: Path, change: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    request = GenerationInput.model_validate_json(data.store.read(event.call.input_ref))
    if change == "parameters":
        changed = event.call.model_copy(
            update={"parameters_ref": put(data.store, {"seed": 0, "temperature": 0})}
        )
    elif change == "missing":
        changed = event.call.model_copy(
            update={
                "input_ref": event.call.input_ref.model_copy(
                    update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
                )
            }
        )
    else:
        if change == "seed":
            request = request.model_copy(update={"seed": request.seed + 1})
        if change == "context":
            request = request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={"context_id": "different"}
                    )
                }
            )
        if change == "skills":
            request = request.model_copy(
                update={"retrieved_skills": tuple(reversed(request.retrieved_skills))}
            )
        input_ref = put(
            data.store,
            {} if change == "invalid_json" else request,
            "generation-input/1",
            "public",
        )
        changed = event.call.model_copy(update={"input_ref": input_ref})
    invalid = CallPlanned(operation=event.operation, call=changed)
    before = snapshot_path(data).read_bytes()
    with pytest.raises((OwnershipConflict, EvidenceNotFound, ValidationError)):
        journal.append(invalid, -1, invalid.operation)
    assert snapshot_path(data).read_bytes() == before


def test_response_raw_content_must_match(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    planned = data.event(progress)
    progress = journal.append(planned, -1, planned.operation)
    event = data.event(progress)
    assert isinstance(event, CallCompleted)
    event = event.model_copy(
        update={
            "response": event.response.model_copy(
                update={"response_ref": put(data.store, {})}
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        journal.append(event, progress.revision, event.operation)
    assert journal.read(command()) == progress


def pending_attempt(data: StorageFixture) -> ConstructionProgress:
    journal = data.journal()
    progress = journal.create(data.plan, command())
    while progress.project().next_action.kind != "await_attempt":
        event = data.event(progress)
        progress = journal.append(event, progress.revision, event.operation)
    return progress


@pytest.mark.parametrize("change", ["evaluation", "execution"])
def test_attempt_persisted_facts_match_inline_result(
    tmp_path: Path, change: str
) -> None:
    data = fixture(tmp_path)
    progress = pending_attempt(data)
    event = data.event(progress)
    assert isinstance(event, AttemptCompleted)
    if change == "evaluation":
        other = event.result.evaluation.model_copy(update={"reason_code": "DIFFERENT"})
        result = event.result.model_copy(
            update={"evaluation_ref": put(data.store, other, "evaluation/1")}
        )
    else:
        result = event.result.model_copy(
            update={"attempt_ref": put(data.store, {}, "attempt-result/1")}
        )
    changed = event.model_copy(update={"result": result})
    with pytest.raises(OwnershipConflict):
        data.journal().append(changed, progress.revision, changed.operation)
    assert data.journal().read(command()) == progress


def test_unknown_judgment_requires_persisted_superseding_evaluation(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    progress = pending_attempt(data)
    event = data.event(progress, status="unknown")
    assert isinstance(event, AttemptCompleted)
    progress = data.journal().append(event, progress.revision, event.operation)
    assert progress.project().next_action.kind == "blocked"
    old = event.result
    evaluation = Evaluation.model_validate(
        old.evaluation.model_copy(
            update={
                "status": "failure",
                "reward": 0,
                "supersedes": old.evaluation_ref,
                "checks": tuple(
                    CheckResult.model_validate(
                        item.model_copy(update={"status": "fail"})
                    )
                    for item in old.evaluation.checks
                ),
            }
        )
    )
    resolved = AttemptResolved(
        operation=command(),
        result=old.model_copy(
            update={
                "evaluation": evaluation,
                "evaluation_ref": put(data.store, evaluation, "evaluation/1"),
            }
        ),
    )
    saved = data.journal().append(resolved, progress.revision, resolved.operation)
    assert saved.project().next_action.kind == "execute"
    assert saved.project().attempts[-1].attempt_ref == old.attempt_ref


@pytest.mark.parametrize("fault", ["missing", "corrupt", "symlink", "fifo"])
def test_used_namespace_cannot_be_reopened_empty(tmp_path: Path, fault: str) -> None:
    import os

    data = fixture(tmp_path)
    creation = command()
    journal = data.journal()
    journal.create(data.plan, creation)
    path = snapshot_path(data)
    path.unlink()
    if fault == "corrupt":
        path.write_text("{}")
    elif fault == "symlink":
        path.symlink_to(tmp_path / "unrelated")
    elif fault == "fifo":
        os.mkfifo(path)
    with pytest.raises(EvidenceIntegrityError):
        data.journal().create(data.plan, creation)


def test_plan_and_capacity_cannot_change_on_reopen(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data.journal().create(data.plan, command())
    with pytest.raises(OwnershipConflict):
        data.journal(capacity=limits(max_events=255)).read(command())
    changed = data.plan.model_copy(
        update={
            "claim_ref": put(
                data.store, {"unit_claim": True, "different": True}, "source-claim/1"
            )
        }
    )
    assert data.journal(plan=changed).file.name == data.journal().file.name
    with pytest.raises(OwnershipConflict):
        data.journal(plan=changed).read(command())


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_events", True),
        ("max_events", 90),
        ("max_events", 257),
        ("max_bytes", 0),
        ("max_bytes", 8 * 1024 * 1024 + 1),
        ("max_event_bytes", 0),
        ("max_event_bytes", 32768.0),
    ],
)
def test_capacity_invalid_types_and_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        limits(**cast(dict[str, int], {field: value}))


def test_actual_envelope_included_in_preflight(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    capacity = limits(max_event_bytes=1024, max_bytes=91 * 1025)
    with pytest.raises(ValidationError, match="completion space"):
        data.journal(capacity=capacity).create(data.plan, command())
    assert list((tmp_path / "journal").iterdir()) == []


def test_full_event_reserve_still_allows_completion(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    journal = data.journal(capacity=limits(max_events=91))
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    progress = journal.append(event, -1, event.operation)
    unknown = put(data.store, {"unknown_request": event.call.request_id})
    for _ in range(5):
        note = CallUncertain(
            operation=command(), request_id=event.call.request_id, evidence_ref=unknown
        )
        try:
            progress = journal.append(note, progress.revision, note.operation)
        except ConstructionCommitUnconfirmed as error:
            assert isinstance(error.__cause__, ValidationError)
            assert (
                TypeAdapter(ProgressEvent).validate_json(
                    data.store.read(error.event_ref)
                )
                == note
            )
            break
    else:
        raise AssertionError("Reserved completion was consumed")
    assert journal.read(command()) == progress
    while progress.project().next_action.kind != "complete":
        event = data.event(progress)
        progress = journal.append(event, progress.revision, event.operation)
    assert progress.project().selection is not None
    assert len(progress.events) <= 91


def test_oversized_observed_fact_retained_but_snapshot_not_truncated(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    capacity = limits(max_event_bytes=2400, max_bytes=512 * 1024)
    journal = data.journal(capacity=capacity)
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    # Size is explicit; select the smallest bound that admits this actual intent.
    bound = len(event.model_dump_json().encode())
    assert bound < 6000
    # No capacity changes to an existing snapshot: use a second independent root.
    second = tmp_path / "second"
    second.mkdir()
    data = fixture(second)
    journal = data.journal(
        capacity=limits(max_event_bytes=bound, max_bytes=1024 * 1024)
    )
    progress = journal.create(data.plan, command())
    planned = data.event(progress)
    progress = journal.append(planned, -1, planned.operation)
    result = data.event(progress)
    assert isinstance(result, CallCompleted)
    # Oversize metadata is valid but cannot fit the frozen event bound.
    response_ref = result.response.response_ref.model_copy(
        update={"media_type": "application/" + "x" * 6000}
    )
    result = result.model_copy(
        update={
            "response": result.response.model_copy(
                update={"response_ref": response_ref}
            )
        }
    )
    before = (second / "journal" / journal.file.name).read_bytes()
    with pytest.raises(ConstructionCommitUnconfirmed) as caught:
        journal.append(result, progress.revision, result.operation)
    assert (
        TypeAdapter(ProgressEvent).validate_json(
            data.store.read(caught.value.event_ref)
        )
        == result
    )
    assert (second / "journal" / journal.file.name).read_bytes() == before
