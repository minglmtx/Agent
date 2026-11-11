"""Complete pure construction flows and prefix replay, never real model calls."""

import hashlib
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    AttemptIntent,
    AttemptPlanned,
    AttemptResolved,
    CallCompleted,
    CallPlanned,
    CallUncertain,
    ConstructionAttemptResult,
    ConstructionCall,
    ConstructionPlan,
    ProgressEvent,
    SelectionCommitted,
    SelectionResult,
)
from lab_generate_skill.domain.construction_inputs import (
    GeneratedCandidate,
    RevisionResult,
)
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    append_construction_event,
    select_target,
)
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evaluation import CheckResult, Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.retrieval import RetrievalScope
from lab_generate_skill.domain.run_plan import ConstructionWorkload

from test_run_journal import command
from test_run_plan import binding, plan


def ref(
    label: str, schema: str = "fixture/1", visibility: str = "private"
) -> EvidenceRef:
    digest = hashlib.sha256(label.encode()).hexdigest()
    return EvidenceRef.model_validate(
        dict(
            uri="cas://sha256/" + digest,
            sha256=digest,
            size_bytes=1,
            media_type="application/json",
            content_schema=schema,
            visibility=visibility,
            producer="unit-construction",
        )
    )


def skill(label: str = "one") -> CompactSkill:
    return CompactSkill(
        title=label,
        principle="Follow the public task and verify the saved result.",
        when_to_apply="When the stated task requires this operation.",
    )


def initial() -> ConstructionProgress:
    run = plan()
    assert isinstance(run.workload, ConstructionWorkload)
    construction = ConstructionPlan.from_run_plan(
        run,
        binding(run),
        "task",
        claim_ref=ref("claim", "source-claim/1"),
        public_context_ref=ref("context", "public-construction-context/1", "public"),
        context_receipt_ref=ref("qualified", "public-context-receipt/1"),
        retrieval_ref=ref("retrieval", "retrieval-result/1"),
        retrieval_scope=RetrievalScope(
            bank_ref=run.workload.bank_ref, split_ref=run.split_manifest_ref
        ),
    )
    return ConstructionProgress(plan=construction)


def append(
    progress: ConstructionProgress, event: ProgressEvent
) -> ConstructionProgress:
    return append_construction_event(progress, event, progress.revision)


def planned_call(progress: ConstructionProgress) -> CallPlanned:
    action = progress.project().next_action
    assert (
        action.kind in ("generate", "revise")
        and action.candidate_slot is not None
        and action.resample_index is not None
    )
    role = "generator" if action.kind == "generate" else "teacher"
    model = next(item for item in progress.plan.models if item.role == role)
    seed, temp = (
        progress.plan.method.generator_sampling(
            action.candidate_slot, action.resample_index
        )
        if role == "generator"
        else (progress.plan.method.teacher_seed(action.candidate_slot - 3), None)
    )
    identifier = f"{role}-{action.candidate_slot}-{action.resample_index}"
    return CallPlanned(
        operation=command(),
        call=ConstructionCall.model_validate(
            dict(
                request_id=identifier,
                role=role,
                candidate_slot=action.candidate_slot,
                resample_index=action.resample_index,
                seed=seed,
                temperature=temp,
                model_binding_ref=model.model_binding_ref,
                base_parameters_ref=model.parameters_ref,
                input_ref=ref(
                    identifier + "-input",
                    "generation-input/1" if role == "generator" else "revision-input/1",
                    "public" if role == "generator" else "teacher",
                ),
                parameters_ref=ref(identifier + "-params"),
            )
        ),
    )


def completed_call(
    progress: ConstructionProgress, content: CompactSkill | None = None
) -> CallCompleted:
    call = progress.project().pending_call
    assert call is not None
    response_type = GeneratedCandidate if call.role == "generator" else RevisionResult
    return CallCompleted(
        operation=command(),
        response=response_type(
            request_id=call.request_id,
            input_sha256=call.input_ref.sha256,
            parameters_sha256=call.parameters_ref.sha256,
            skill=content or skill(call.request_id),
            response_ref=ref(call.request_id + "-response"),
        ),
    )


def planned_attempt(progress: ConstructionProgress) -> AttemptPlanned:
    view = progress.project()
    slot = view.next_action.candidate_slot
    assert slot is not None
    return AttemptPlanned(
        operation=command(),
        intent=AttemptIntent(
            binding=AttemptBinding(
                run=progress.plan.run,
                attempt_id=f"attempt-{slot}",
                task=progress.plan.task.identity,
                claim_ref=progress.plan.claim_ref,
            ),
            candidate_slot=slot,
            skill_digest=view.candidates[slot].response.skill.content_digest,
            public_context_ref=progress.plan.public_context_ref,
        ),
    )


def completed_attempt(
    progress: ConstructionProgress, status: str = "failure", steps: int = 5
) -> AttemptCompleted:
    intent = progress.project().pending_attempt
    assert intent is not None
    evaluation = Evaluation.model_validate(
        dict(
            identity=intent.binding.task,
            attempt_id=intent.binding.attempt_id,
            contract_ref=ref("contract"),
            evaluator_id="unit",
            evaluator_version="1",
            status=status,
            reward={"success": 1, "failure": 0, "unknown": None}[status],
            checks=(
                CheckResult.model_validate(
                    dict(
                        name="goal",
                        status={
                            "success": "pass",
                            "failure": "fail",
                            "unknown": "unknown",
                        }[status],
                        reason_code="UNIT",
                        evidence=(ref("fact"),),
                    )
                ),
            ),
            reason_code="UNIT",
        )
    )
    return AttemptCompleted(
        operation=command(),
        result=ConstructionAttemptResult(
            intent=intent,
            attempt_ref=ref(intent.binding.attempt_id, "attempt-result/1"),
            evaluation=evaluation,
            evaluation_ref=ref(
                intent.binding.attempt_id + "-evaluation", "evaluation/1"
            ),
            interactions=steps,
            generations=steps + 1,
        ),
    )


def advance(
    progress: ConstructionProgress,
    status: str = "failure",
    steps: int = 5,
    duplicate: bool = False,
) -> ConstructionProgress:
    action = progress.project().next_action
    if action.kind in ("generate", "revise"):
        progress = append(progress, planned_call(progress))
        return append(
            progress, completed_call(progress, skill("same") if duplicate else None)
        )
    if action.kind == "execute":
        progress = append(progress, planned_attempt(progress))
        return append(progress, completed_attempt(progress, status, steps))
    if action.kind == "select":
        return append(
            progress,
            SelectionCommitted(
                operation=command(),
                selection=select_target(progress.project().attempts),
            ),
        )
    raise AssertionError(action)


def finish(status: str = "failure", duplicate: bool = False) -> ConstructionProgress:
    progress = initial()
    for _ in range(50):
        if progress.project().next_action.kind == "complete":
            return progress
        progress = advance(progress, status, duplicate=duplicate)
    raise AssertionError("Construction failed to terminate within method bound")


def test_all_failure_runs_three_teacher_rounds_then_rejects() -> None:
    result = finish()
    view = result.project()
    assert len(view.candidates) == len(view.attempts) == 7
    assert view.selection == SelectionResult(status="rejected")
    assert (
        len([event for event in result.events if isinstance(event, CallPlanned)]) == 7
    )


def test_success_still_runs_first_teacher_and_stable_earliest_tie() -> None:
    result = finish("success")
    view = result.project()
    assert len(view.attempts) == 5
    assert view.selection is not None and view.selection.candidate_slot == 0
    assert (
        sum(
            isinstance(event, CallPlanned) and event.call.role == "teacher"
            for event in result.events
        )
        == 1
    )


def test_later_success_uses_fewer_environment_returns() -> None:
    progress = initial()
    while progress.project().next_action.kind != "select":
        slot = progress.project().next_action.candidate_slot or 0
        progress = advance(progress, "success", steps=6 - slot)
    progress = advance(progress)
    selected = progress.project().selection
    assert selected is not None and selected.candidate_slot == 4


def test_duplicate_resampling_cap_retains_last_duplicate() -> None:
    result = finish(duplicate=True)
    calls = [
        event.call
        for event in result.events
        if isinstance(event, CallPlanned) and event.call.role == "generator"
    ]
    assert len(calls) == 16  # first unique + three candidates with five tries each
    assert [item.resample_index for item in calls if item.candidate_slot == 1] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert (
        len(
            {
                candidate.response.skill.content_digest
                for candidate in result.project().candidates
            }
        )
        == 1
    )
    assert len(result.project().attempts) == 7


@pytest.mark.parametrize("status", ["success", "failure"])
def test_replay_from_every_saved_prefix_matches_uninterrupted(status: str) -> None:
    complete = finish(status)
    for length in range(len(complete.events) + 1):
        prefix = ConstructionProgress(
            plan=complete.plan, events=complete.events[:length]
        )
        restored = ConstructionProgress.model_validate_json(prefix.model_dump_json())
        for event in complete.events[length:]:
            restored = append(restored, event)
        assert restored == complete
        assert restored.project() == complete.project()


def test_uncertain_registered_call_never_schedules_resend() -> None:
    progress = initial()
    event = planned_call(progress)
    progress = append(progress, event)
    progress = append(
        progress,
        CallUncertain(
            operation=command(),
            request_id=event.call.request_id,
            evidence_ref=ref("unknown"),
        ),
    )
    assert progress.project().next_action.kind == "await_response"
    with pytest.raises((InvalidTransition, ValidationError)):
        append(progress, CallPlanned(operation=command(), call=event.call))
    restored = ConstructionProgress.model_validate_json(progress.model_dump_json())
    restored = append(restored, completed_call(restored))
    assert restored.project().next_action.candidate_slot == 1


def test_unknown_attempt_can_only_resume_with_superseding_judgment() -> None:
    progress = initial()
    while progress.project().next_action.kind == "generate":
        progress = advance(progress)
    progress = advance(progress, "unknown")
    assert progress.project().next_action.kind == "blocked"
    previous = progress.project().attempts[-1]
    with pytest.raises(InvalidTransition):
        select_target(progress.project().attempts)
    evaluation = Evaluation.model_validate(
        previous.evaluation.model_copy(
            update={
                "status": "success",
                "reward": 1,
                "checks": (
                    CheckResult(
                        name="goal",
                        status="pass",
                        reason_code="REVIEWED",
                        evidence=(ref("review"),),
                    ),
                ),
                "supersedes": previous.evaluation_ref,
            }
        )
    )
    corrected = ConstructionAttemptResult.model_validate(
        previous.model_copy(
            update={
                "evaluation": evaluation,
                "evaluation_ref": ref("reviewed", "evaluation/1"),
            }
        )
    )
    progress = append(progress, AttemptResolved(operation=command(), result=corrected))
    assert (
        progress.project().next_action.kind == "execute"
        and progress.project().next_action.candidate_slot == 1
    )
    assert len(progress.project().attempts) == 1


def test_exact_replay_stale_revision_and_changed_operation() -> None:
    first = initial()
    event = planned_call(first)
    saved = append(first, event)
    assert append_construction_event(saved, event, -1) == saved
    with pytest.raises(RevisionConflict):
        append_construction_event(saved, completed_call(saved), -1)
    changed = event.model_copy(
        update={"call": event.call.model_copy(update={"request_id": "changed"})}
    )
    with pytest.raises(OwnershipConflict):
        append_construction_event(saved, changed, saved.revision)


@pytest.mark.parametrize("revision", [True, -2, 1.0, "0", None])
def test_invalid_revision(revision: object) -> None:
    value = initial()
    with pytest.raises(ValueError):
        append_construction_event(value, planned_call(value), cast(int, revision))


@pytest.mark.parametrize(
    "change",
    [
        {"seed": 0},
        {"temperature": 1.2},
        {"candidate_slot": 1},
        {"resample_index": 1},
        {"model_binding_ref": ref("other")},
    ],
)
def test_call_schedule_and_binding_cannot_change(change: dict[str, object]) -> None:
    value = initial()
    event = planned_call(value)
    changed = CallPlanned(
        operation=event.operation,
        call=ConstructionCall.model_validate(event.call.model_copy(update=change)),
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        append(value, changed)


@pytest.mark.parametrize("field", ["request_id", "input_sha256", "parameters_sha256"])
def test_wrong_response_cannot_complete_call(field: str) -> None:
    value = initial()
    value = append(value, planned_call(value))
    event = completed_call(value)
    replacement = "wrong" if field == "request_id" else "f" * 64
    changed = GeneratedCandidate.model_validate(
        event.response.model_copy(update={field: replacement})
    )
    with pytest.raises(OwnershipConflict):
        append(value, CallCompleted(operation=event.operation, response=changed))


def test_sealed_history_allows_old_replay_but_no_new_work() -> None:
    result = finish("success")
    assert append_construction_event(result, result.events[0], -1) == result
    with pytest.raises((InvalidTransition, ValidationError)):
        append(
            result,
            SelectionCommitted(
                operation=command(), selection=SelectionResult(status="rejected")
            ),
        )


def test_cannot_skip_mandatory_teacher_or_select_wrong_target() -> None:
    progress = initial()
    while len(progress.project().attempts) < 4:
        progress = advance(progress, "success")
    with pytest.raises((InvalidTransition, ValidationError)):
        append(
            progress,
            SelectionCommitted(
                operation=command(),
                selection=select_target(progress.project().attempts),
            ),
        )
    while progress.project().next_action.kind != "select":
        progress = advance(progress, "success")
    with pytest.raises((InvalidTransition, ValidationError)):
        append(
            progress,
            SelectionCommitted(
                operation=command(), selection=SelectionResult(status="rejected")
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"owner_id": "other"},
        {"run_id": "other"},
        {"attempt_id": "attempt"},
        {"mode": "cleanup", "parent_operation_id": "parent"},
    ],
)
def test_wrong_operation_scope_or_cleanup_cannot_schedule(
    change: dict[str, object],
) -> None:
    progress = initial()
    event = planned_call(progress)
    changed = event.model_copy(
        update={"operation": event.operation.model_copy(update=change)}
    )
    with pytest.raises((OwnershipConflict, ValueError)):
        append(progress, changed)


@pytest.mark.parametrize("change", ["context", "claim", "skill", "slot", "task"])
def test_attempt_intent_must_bind_candidate_and_baseline(change: str) -> None:
    progress = initial()
    while progress.project().next_action.kind == "generate":
        progress = advance(progress)
    event = planned_attempt(progress)
    fields = event.intent.model_dump(mode="python")
    if change == "context":
        fields["public_context_ref"] = ref(
            "other", "public-construction-context/1", "public"
        )
    elif change == "claim":
        fields["binding"] = event.intent.binding.model_copy(
            update={"claim_ref": ref("other")}
        )
    elif change == "skill":
        fields["skill_digest"] = "f" * 64
    elif change == "slot":
        fields["candidate_slot"] = 1
    else:
        fields["binding"] = event.intent.binding.model_copy(
            update={
                "task": event.intent.binding.task.model_copy(
                    update={"task_id": "other"}
                )
            }
        )
    intent = AttemptIntent.model_validate(fields)
    with pytest.raises((OwnershipConflict, ValueError)):
        append(progress, AttemptPlanned(operation=event.operation, intent=intent))


def test_unplanned_response_and_duplicate_attempt_result_rejected() -> None:
    progress = initial()
    pending = append(progress, planned_call(progress))
    response = completed_call(pending)
    with pytest.raises(ValueError):
        append(progress, response)
    while progress.project().next_action.kind == "generate":
        progress = advance(progress)
    pending = append(progress, planned_attempt(progress))
    result = completed_attempt(pending)
    saved = append(pending, result)
    with pytest.raises(OwnershipConflict):
        append(saved, AttemptCompleted(operation=command(), result=result.result))


def test_attempt_result_cannot_exceed_run_limits() -> None:
    progress = initial()
    while progress.project().next_action.kind == "generate":
        progress = advance(progress)
    pending = append(progress, planned_attempt(progress))
    result = completed_attempt(pending, steps=17)
    with pytest.raises(ValueError):
        append(pending, result)


def test_unknown_resolution_cannot_rewrite_execution_or_omit_supersedes() -> None:
    progress = initial()
    while progress.project().next_action.kind == "generate":
        progress = advance(progress)
    progress = advance(progress, "unknown")
    prior = progress.project().attempts[-1]
    with pytest.raises(OwnershipConflict):
        append(progress, AttemptResolved(operation=command(), result=prior))
    changed = ConstructionAttemptResult.model_validate(
        prior.model_copy(
            update={
                "interactions": 4,
                "evaluation": prior.evaluation.model_copy(
                    update={"supersedes": prior.evaluation_ref}
                ),
                "evaluation_ref": ref("next", "evaluation/1"),
            }
        )
    )
    with pytest.raises(OwnershipConflict):
        append(progress, AttemptResolved(operation=command(), result=changed))


def test_uncertainty_cannot_exhaust_result_and_selection_capacity() -> None:
    progress = initial()
    event = planned_call(progress)
    progress = append(progress, event)
    for _ in range(256):
        uncertain = CallUncertain(
            operation=command(),
            request_id=event.call.request_id,
            evidence_ref=ref("unknown"),
        )
        try:
            candidate = append(progress, uncertain)
        except ValidationError as error:
            assert any(
                "retain result and selection" in item["msg"] for item in error.errors()
            )
            break
        progress = candidate
    else:
        raise AssertionError("Uncertainty exhausted the reserved completion space")
    assert progress.revision > 100
    progress = append(progress, completed_call(progress))
    while progress.project().next_action.kind != "complete":
        progress = advance(progress)
    assert progress.project().selection == SelectionResult(status="rejected")
    assert len(progress.events) <= 256


def test_replay_validates_types_before_python_equality() -> None:
    value = initial()
    event = planned_call(value)
    saved = append(value, event)
    changed = event.model_copy(
        update={"call": event.call.model_copy(update={"seed": float(event.call.seed)})}
    )
    # Numeric equality is not sufficient for well-typed exact replay.
    assert changed == event
    with pytest.raises(ValidationError):
        append_construction_event(saved, changed, -1)


@pytest.mark.parametrize("value", [None, [], {"kind": "invented"}])
def test_invalid_event_payload_rejected_before_projection(value: object) -> None:
    with pytest.raises(ValidationError):
        append_construction_event(initial(), cast(ProgressEvent, value), -1)


def test_selector_revalidates_result_and_container_types() -> None:
    result = finish("success").project().attempts[0]
    changed = result.model_copy(update={"interactions": True})
    with pytest.raises(ValidationError):
        select_target((changed,))
    with pytest.raises(ValidationError):
        select_target(cast(tuple[ConstructionAttemptResult, ...], [result]))
    assert select_target(()) == SelectionResult(status="rejected")
