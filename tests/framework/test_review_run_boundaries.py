"""Review never repairs/replays original requests or promotes unit/unknown data."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.application.review_run import (
    review_run,
    ReviewUnconfirmed,
    ReviewEvaluator,
)
from lab_generate_skill.domain.review import ReviewPlan, ReviewReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import Evaluation
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from construction_review_fixtures import (
    ReviewCase,
    UnitWorld,
    UnitReplayEvaluator,
    construction_review_case,
)
from construction_storage_fixtures import put


@pytest.fixture(scope="module")
def ready(tmp_path_factory: pytest.TempPathFactory) -> ReviewCase:
    with pytest.MonkeyPatch.context() as patch:
        return construction_review_case(
            tmp_path_factory.mktemp("construction-review") / "case", patch
        )


@pytest.mark.parametrize("bad", [None, {}, [], "", True, 0])
def test_invalid_review_commands_fail_before_reading_or_execution(
    ready: ReviewCase, bad: Any
) -> None:
    absent: Any = None
    with pytest.raises(ValidationError):
        review_run(bad, absent)
    assert ready.control.source.native.loader.session.calls == 5


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "run-plan",
        "execution-release",
        "judgment-release",
        "scope",
        "attempt",
        "read-mode",
        "extended-deadline",
        "drop-cancel",
        "duplicate-task",
        "missing-task",
        "teacher-round",
        "selected-evaluation",
        "source-visibility",
        "source-oversize",
    ],
)
def test_review_schema_scope_full_history_and_explicit_branch(
    ready: ReviewCase, fault: str
) -> None:
    plan = ready.plan("schema-" + fault)
    data: dict[str, Any] = plan.model_dump()
    if fault == "version":
        data["schema_version"] = "construction-review-plan/0"
    elif fault in ("run-plan", "execution-release", "judgment-release"):
        key = {
            "run-plan": "original_run_plan_ref",
            "execution-release": "original_execution_release",
            "judgment-release": "judgment_release",
        }[fault]
        data[key] = getattr(plan, key).model_copy(update={"sha256": "0" * 64})
    elif fault in ("scope", "attempt"):
        data["operation"] = plan.operation.model_copy(
            update=(
                {"owner_id": "foreign"}
                if fault == "scope"
                else {"attempt_id": "foreign"}
            )
        )
    elif fault in ("read-mode", "extended-deadline"):
        read = plan.tasks[0].operation.model_copy(
            update=(
                {"mode": "execute", "parent_operation_id": None}
                if fault == "read-mode"
                else {"deadline": plan.operation.deadline + timedelta(seconds=1)}
            )
        )
        data["tasks"] = (
            plan.tasks[0].model_copy(update={"operation": read}),
            *plan.tasks[1:],
        )
    elif fault == "drop-cancel":
        from lab_generate_skill.domain.lifecycle import CancellationRef

        data["operation"] = plan.operation.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="cancel-review",
                    run_id=plan.operation.run_id,
                    owner_id=plan.operation.owner_id,
                )
            }
        )
    elif fault == "duplicate-task":
        data["tasks"] = (plan.tasks[0], plan.tasks[0], *plan.tasks[2:])
    elif fault == "missing-task":
        data["tasks"] = plan.tasks[:-1]
    elif fault == "teacher-round":
        data["teachers"] = (*plan.teachers, plan.teachers[0])
    elif fault == "selected-evaluation":
        data["selected_evaluation_ref"] = None
    else:
        data["sealed_evidence_ref"] = plan.sealed_evidence_ref.model_copy(
            update=(
                {"visibility": "public"}
                if fault == "source-visibility"
                else {"size_bytes": 8 * 1024**2 + 1}
            )
        )
    with pytest.raises(ValidationError):
        ReviewPlan.model_validate(data)


@pytest.mark.parametrize(
    "outcome,expected",
    [("failure", "inconsistent"), ("unknown", "insufficient_evidence")],
)
def test_independent_judgment_difference_or_missing_fact_never_changes_original_or_exports_target(
    ready: ReviewCase, outcome: str, expected: str
) -> None:
    plan = ready.plan("reproduced-" + outcome)
    deps = ready.deps(plan)
    store = ready.control.source.data.store
    # Separate immutable unit environment evidence, not the saved worker verdict.
    world = UnitWorld.model_validate(
        {
            "statuses": {
                **{"attempt-" + str(i): "failure" for i in range(4)},
                "attempt-4": outcome,
            }
        }
    )
    ref = put(store, world, "unit-review-world/1")
    altered = replace(
        deps,
        evaluators=tuple(
            ReviewEvaluator(e.attempt_id, UnitReplayEvaluator(ref))
            for e in deps.evaluators
        ),
    )
    receipt = review_run(plan, altered)
    assert receipt.status == expected and receipt.selected_skill_ref is None
    assert receipt.training_admission == "not_evaluated"
    assert receipt.findings[-1].reproduced.status == outcome
    assert ready.sealed.project().attempts[-1].evaluation.status == "success"
    assert ready.control.source.data.journal().read(plan.operation) == ready.sealed


@pytest.mark.parametrize(
    "fault",
    [
        "selected-ref",
        "swapped-branches",
        "history",
        "missing-evaluator",
        "runtime",
        "task-parent",
        "teacher-parent",
        "unsealed",
    ],
)
def test_review_binding_and_permissions_fail_without_any_new_execution(
    ready: ReviewCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    plan = ready.plan("binding-" + fault)
    if fault == "selected-ref":
        plan = plan.model_copy(
            update={
                "selected_evaluation_ref": ready.sealed.project()
                .attempts[0]
                .evaluation_ref
            }
        )
    elif fault == "swapped-branches":
        tasks = list(plan.tasks)
        tasks[-1] = tasks[-1].model_copy(update={"published": tasks[0].published})
        plan = plan.model_copy(update={"tasks": tuple(tasks)})
        with pytest.raises(ValidationError):
            review_run(plan, ready.deps(ready.plan("unused-swapped")))
        return
    elif fault in ("task-parent", "teacher-parent"):
        field = "tasks" if fault == "task-parent" else "teachers"
        items = getattr(plan, field)
        plan = plan.model_copy(
            update={
                field: (
                    items[0].model_copy(
                        update={
                            "operation": items[0].operation.model_copy(
                                update={"parent_operation_id": "foreign"}
                            )
                        }
                    ),
                    *items[1:],
                )
            }
        )
    elif fault == "unsealed":
        prefix = ready.sealed.model_copy(update={"events": ready.sealed.events[:-1]})
        plan = plan.model_copy(
            update={
                "sealed_evidence_ref": put(
                    ready.control.source.data.store, prefix, "construction-progress/1"
                )
            }
        )
    if fault == "teacher-parent":
        with pytest.raises(ValueError):
            ready.deps(plan)
        return
    deps = ready.deps(plan)
    if fault == "history":
        original = deps.history.verify

        def denied(*args: Any) -> None:
            raise EvidenceIntegrityError(
                "original recorded source/Generator proof differs"
            )

        monkeypatch.setattr(deps.history, "verify", denied)
    elif fault == "missing-evaluator":
        deps = replace(deps, evaluators=deps.evaluators[:-1])
    elif fault == "runtime":
        monkeypatch.setattr(ready.authority, "denied", True)
    with pytest.raises(ReviewUnconfirmed) as caught:
        review_run(plan, deps)
    assert caught.value.primary is not None
    assert ready.control.source.native.loader.session.calls == 5
    assert len(ready.control.wire.transport.calls) == 1


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_original_review_stop_preserves_cause_and_never_executes(
    ready: ReviewCase, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    plan = ready.plan("stop-" + reason)
    deps = ready.deps(plan)
    error = OperationStopped(reason, plan.operation.operation_id)

    def stopped() -> float:
        raise error

    monkeypatch.setattr(deps.controls.bind(plan.operation), "checkpoint", stopped)
    with pytest.raises(ReviewUnconfirmed) as caught:
        review_run(plan, deps)
    assert caught.value.primary is error and not caught.value.completed


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_missing_or_corrupt_deep_native_evidence_is_not_a_valid_failure_or_repair(
    ready: ReviewCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    plan = ready.plan("evidence-" + fault)
    deps = ready.deps(plan)
    store = ready.control.source.data.store
    original = store.read
    missing = ready.parts[0].part.source.trace_ref
    error = EvidenceNotFound("original native trace absent")

    def read(ref: EvidenceRef, control: Any = None) -> bytes:
        if ref == missing:
            if fault == "missing":
                raise error
            return b"{}"
        return original(ref, control)

    monkeypatch.setattr(store, "read", read)
    with pytest.raises(ReviewUnconfirmed) as caught:
        review_run(plan, deps)
    if fault == "missing":
        assert caught.value.primary is error
    else:
        assert caught.value.primary is not None
    assert ready.control.source.native.loader.session.calls == 5


def test_fresh_read_scope_after_original_teacher_deadline_keeps_original_send_and_no_model(
    ready: ReviewCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    deadline = ready.teacher.bound.plan.send.settlement_operation.deadline
    now = deadline + timedelta(seconds=1)
    monkeypatch.setattr(SystemClock, "utcnow", lambda self: now)
    plan = ready.plan("after-old-send-expiry", now=now)
    result = review_run(plan, ready.deps(plan))
    assert result.status == "verified"
    assert ready.teacher.bound.plan.send.settlement_operation.deadline == deadline
    assert (
        ready.control.source.native.loader.session.calls == 5
        and len(ready.control.wire.transport.calls) == 1
    )


def test_self_consistent_CAS_fork_cannot_replace_original_committed_history(
    ready: ReviewCase,
) -> None:
    final = ready.sealed.events[-1]
    changed = final.model_copy(
        update={
            "operation": final.operation.model_copy(
                update={"operation_id": "not-the-original-selection"}
            )
        }
    )
    forged = ready.sealed.model_copy(
        update={"events": (*ready.sealed.events[:-1], changed)}
    )
    ref = put(ready.control.source.data.store, forged, "construction-progress/1")
    case = replace(ready, sealed=forged, source_ref=ref)
    plan = case.plan("forged-CAS-history")
    with pytest.raises(ReviewUnconfirmed) as caught:
        review_run(plan, case.deps(plan))
    assert isinstance(caught.value.primary, EvidenceIntegrityError)
    assert "original persisted construction" in str(caught.value.primary)
    assert ready.control.source.data.journal().read(plan.operation) == ready.sealed
