"""Independent state/action matrix, original identities, restart and replay."""

from itertools import product
from datetime import timedelta
from typing import Literal, cast
import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionEntry,
    EvidenceSessionResolution,
    EvidenceWorkerInstance,
)
from lab_generate_skill.domain.evidence_session_state import (
    EvidenceSessionSnapshot,
    begin_evidence_exchange,
    record_evidence_outcome,
    resolve_evidence_exchange,
)
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
    EvidenceNotFound,
)
from evidence_session_fixtures import (
    binding,
    capacity,
    intent,
    outcome,
    resolution,
    pending,
)


def in_stage(stage: str) -> EvidenceSessionSnapshot:
    snapshot = pending()
    if stage == "returned":
        return record_evidence_outcome(snapshot, outcome(intent()), snapshot.revision)
    if stage in {"quarantined", "resolved"}:
        return resolve_evidence_exchange(
            snapshot, resolution(intent(), ended=stage == "resolved"), snapshot.revision
        )
    return snapshot


@pytest.mark.parametrize(
    "stage,action",
    list(
        product(
            ["pending", "returned", "quarantined", "resolved"],
            ["begin", "outcome", "resolve"],
        )
    ),
)
def test_state_action_matrix(stage: str, action: str) -> None:
    # Independent contract expectations, not generated from production predicates.
    allowed = {
        ("resolved", "begin"),
        ("pending", "outcome"),
        ("pending", "resolve"),
        ("returned", "resolve"),
        ("quarantined", "resolve"),
    }
    snapshot = in_stage(stage)
    assert snapshot.entries[-1].stage == stage

    def act() -> EvidenceSessionSnapshot:
        if action == "begin":
            return begin_evidence_exchange(snapshot, intent(2), snapshot.revision)
        if action == "outcome":
            fact = outcome(intent()).model_copy(update={"outcome_id": "new-outcome"})
            return record_evidence_outcome(snapshot, fact, snapshot.revision)
        return resolve_evidence_exchange(
            snapshot, resolution(intent(), 2), snapshot.revision
        )

    if (stage, action) in allowed:
        changed = act()
        assert changed.revision == snapshot.revision + 1
    else:
        with pytest.raises((InvalidTransition, OwnershipConflict)):
            act()


@pytest.mark.parametrize(
    "ended,object_state,cleanup_state",
    list(
        product(
            [False, True],
            ["present", "absent", "unknown"],
            ["clean", "failed", "unknown"],
        )
    ),
)
def test_unknown_outcome_reuse_requires_independent_three_facts(
    ended: bool, object_state: str, cleanup_state: str
) -> None:
    snapshot = pending()
    result = resolution(
        intent(),
        ended=ended,
        object_state=cast(Literal["present", "absent", "unknown"], object_state),
        cleanup_state=cast(Literal["clean", "failed", "unknown"], cleanup_state),
    )
    changed = resolve_evidence_exchange(snapshot, result, snapshot.revision)
    safe = ended and object_state in {"present", "absent"} and cleanup_state == "clean"
    assert changed.entries[-1].reusable is safe
    assert changed.entries[-1].outcome is None  # never turn unknown into success
    if not safe:
        with pytest.raises(InvalidTransition):
            begin_evidence_exchange(changed, intent(2), changed.revision)


def test_reply_is_not_exit_and_successful_reply_cannot_reconcile_missing_object() -> (
    None
):
    snapshot = record_evidence_outcome(pending(), outcome(intent()), 1)
    assert (
        snapshot.entries[-1].stage == "returned" and not snapshot.entries[-1].reusable
    )
    changed = resolve_evidence_exchange(
        snapshot, resolution(intent(), object_state="absent"), snapshot.revision
    )
    assert changed.entries[-1].stage == "quarantined"
    closed = resolve_evidence_exchange(
        changed, resolution(intent(), 2), changed.revision
    )
    assert (
        closed.entries[-1].stage == "resolved"
        and closed.entries[-1].outcome == snapshot.entries[-1].outcome
    )


def test_failed_read_can_release_after_exact_end_absence_and_cleanup_without_success_rewrite() -> (
    None
):
    original = intent(kind="read")
    snapshot = begin_evidence_exchange(
        EvidenceSessionSnapshot(binding=binding(), capacity=capacity()), original, 0
    )
    snapshot = record_evidence_outcome(
        snapshot, outcome(original, succeeded=False), snapshot.revision
    )
    snapshot = resolve_evidence_exchange(
        snapshot, resolution(original, object_state="absent"), snapshot.revision
    )
    assert snapshot.entries[-1].reusable and snapshot.entries[-1].outcome is not None
    assert snapshot.entries[-1].outcome.status == "failed"


def test_restart_replay_original_facts_never_resends_or_releases_early() -> None:
    snapshot = pending()
    stopped = resolution(
        intent(), ended=False, object_state="unknown", cleanup_state="unknown"
    )
    snapshot = resolve_evidence_exchange(snapshot, stopped, 1)
    reopened = EvidenceSessionSnapshot.model_validate_json(snapshot.model_dump_json())
    assert reopened == snapshot
    assert resolve_evidence_exchange(reopened, stopped, 0) == snapshot
    with pytest.raises(DispatchAlreadyCommitted):
        begin_evidence_exchange(reopened, intent(), 0)
    completed = resolution(intent(), 2)
    resolved = resolve_evidence_exchange(reopened, completed, reopened.revision)
    later = begin_evidence_exchange(resolved, intent(2), resolved.revision)
    assert resolve_evidence_exchange(later, completed, 0) == later
    with pytest.raises(DispatchAlreadyCommitted):
        begin_evidence_exchange(later, intent(), 0)
    with pytest.raises(InvalidTransition):
        record_evidence_outcome(later, outcome(intent()), later.revision)


def test_changed_facts_are_not_idempotent_replay() -> None:
    snapshot = record_evidence_outcome(pending(), outcome(intent()), 1)
    assert record_evidence_outcome(snapshot, outcome(intent()), 0) == snapshot
    with pytest.raises(OwnershipConflict):
        record_evidence_outcome(
            snapshot, outcome(intent(), succeeded=False), snapshot.revision
        )
    closed = resolve_evidence_exchange(
        snapshot, resolution(intent()), snapshot.revision
    )
    with pytest.raises(OwnershipConflict):
        resolve_evidence_exchange(
            closed, resolution(intent(), object_state="absent"), closed.revision
        )
    with pytest.raises(OwnershipConflict):
        begin_evidence_exchange(
            closed,
            intent().model_copy(update={"command_sha256": "f" * 64}),
            closed.revision,
        )
    with pytest.raises(RevisionConflict):
        record_evidence_outcome(closed, outcome(intent()), True)
    with pytest.raises(RevisionConflict):
        resolve_evidence_exchange(closed, resolution(intent()), True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "other-run"),
        ("owner_id", "other-owner"),
        ("attempt_id", "other-attempt"),
        ("allocation_id", "other-allocation"),
        ("parent_operation_id", "other-parent"),
    ],
)
def test_cleanup_cannot_change_original_scope(field: str, value: str) -> None:
    fact = resolution(intent())
    fact = fact.model_copy(
        update={"operation": fact.operation.model_copy(update={field: value})}
    )
    with pytest.raises(ValidationError):
        resolve_evidence_exchange(pending(), fact, 1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("node_id", "node-2"),
        ("boot_id", "boot-2"),
        ("process_id", 999),
        ("start_ticks", 99999),
    ],
)
def test_pid_reuse_or_foreign_incarnation_cannot_resolve(
    field: str, value: object
) -> None:
    fact = resolution(intent())
    assert fact.worker_end is not None
    wrong = fact.worker_end.model_copy(
        update={"worker": fact.worker_end.worker.model_copy(update={field: value})}
    )
    with pytest.raises(ValidationError):
        resolve_evidence_exchange(
            pending(), fact.model_copy(update={"worker_end": wrong}), 1
        )


@pytest.mark.parametrize("expected", [-1, 0, 2, True, "1", None])
def test_stale_or_wrong_revision_rejected(expected: object) -> None:
    with pytest.raises(RevisionConflict):
        resolve_evidence_exchange(pending(), resolution(intent()), cast(int, expected))


def test_namespace_cannot_be_bypassed_by_new_owner_or_session_id() -> None:
    original = binding()
    for changed in (
        original.model_copy(update={"session_id": "new-session"}),
        original.model_copy(
            update={"owner": original.owner.model_copy(update={"run_id": "new-run"})}
        ),
    ):
        assert changed.namespace_key == original.namespace_key and changed != original
    assert (
        original.model_copy(update={"source_task_id": "source-2"}).namespace_key
        != original.namespace_key
    )
    # This key is not authorization to select a different physical root.
    with pytest.raises(ValidationError):
        begin_evidence_exchange(
            EvidenceSessionSnapshot(
                binding=binding().model_copy(
                    update={
                        "owner": binding().owner.model_copy(update={"run_id": "other"})
                    }
                ),
                capacity=capacity(),
            ),
            intent(),
            0,
        )


def test_bad_snapshot_history_and_reused_worker_rejected() -> None:
    unresolved = pending()
    with pytest.raises(ValidationError):
        EvidenceSessionSnapshot(
            binding=binding(),
            capacity=capacity(),
            entries=(*unresolved.entries, EvidenceSessionEntry(intent=intent(2))),
        )
    closed = resolve_evidence_exchange(unresolved, resolution(intent()), 1)
    with pytest.raises(ValidationError):
        begin_evidence_exchange(
            closed,
            intent(2).model_copy(update={"worker": intent().worker}),
            closed.revision,
        )
    with pytest.raises(EvidenceNotFound):
        record_evidence_outcome(unresolved, outcome(intent(2)), 1)
    with pytest.raises(EvidenceNotFound):
        resolve_evidence_exchange(unresolved, resolution(intent(2)), 1)


@pytest.mark.parametrize("value", [0, -1, True, "1", None])
def test_worker_pid_is_strict_positive_integer(value: object) -> None:
    worker = intent().worker
    with pytest.raises(ValidationError):
        EvidenceWorkerInstance.model_validate(
            worker.model_copy(update={"process_id": value})
        )


@pytest.mark.parametrize("first_kind", ["read", "put"])
def test_distinct_exchanges_share_exact_bound_operation(
    first_kind: Literal["read", "put"],
) -> None:
    first = intent(kind=first_kind)
    first = first.model_copy(
        update={
            "operation": first.operation.model_copy(
                update={"deadline": first.operation.deadline + timedelta(hours=1)}
            )
        }
    )
    snapshot = begin_evidence_exchange(
        EvidenceSessionSnapshot(binding=binding(), capacity=capacity()), first, 0
    )
    snapshot = resolve_evidence_exchange(snapshot, resolution(first), snapshot.revision)
    second = intent(2, "read").model_copy(update={"operation": first.operation})
    snapshot = begin_evidence_exchange(snapshot, second, snapshot.revision)
    snapshot = record_evidence_outcome(snapshot, outcome(second), snapshot.revision)
    snapshot = resolve_evidence_exchange(
        snapshot, resolution(second), snapshot.revision
    )
    assert snapshot.entries[-1].reusable
    assert snapshot.entries[0].intent.operation == snapshot.entries[1].intent.operation
    assert (
        snapshot.entries[0].intent.exchange_id != snapshot.entries[1].intent.exchange_id
    )
    assert (
        EvidenceSessionSnapshot.model_validate_json(snapshot.model_dump_json())
        == snapshot
    )
    with pytest.raises(DispatchAlreadyCommitted):
        begin_evidence_exchange(snapshot, second, snapshot.revision)


@pytest.mark.parametrize("field", ["deadline", "attempt_id", "allocation_id"])
def test_same_operation_id_cannot_change_bound_context(field: str) -> None:
    snapshot = resolve_evidence_exchange(pending(), resolution(intent()), 1)
    original = intent().operation
    value: object = (
        original.deadline + timedelta(seconds=1) if field == "deadline" else "changed"
    )
    second = intent(2).model_copy(
        update={"operation": original.model_copy(update={field: value})}
    )
    with pytest.raises(ValidationError):
        begin_evidence_exchange(snapshot, second, snapshot.revision)
