"""Original-leaf producer and independent export; all permissions synthetic."""

from dataclasses import replace
from pathlib import Path
from typing import cast
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_attempt import (
    publish_teacher_attempt,
    TeacherAttemptUnconfirmed,
)
from lab_generate_skill.application.teacher_attempt_review import review_teacher_attempt
from lab_generate_skill.application.teacher_actor_reads import read_actor_material
from lab_generate_skill.domain.teacher_attempt import (
    TeacherAttemptInput,
    TeacherAttemptReceipt,
    PublishedTeacherAttempt,
)
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_json import object_value, array_value, read_json
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.ports.lifecycle import OperationControl
from teacher_attempt_fixtures import native_attempt_case, cleanup, put


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
@pytest.mark.parametrize("v2", [False, True])
def test_original_native_leaves_full_visible_input_results_feedback_and_independent_read(
    tmp_path: Path, site: Site, v2: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = native_attempt_case(tmp_path / "case", site, request_v2=v2)
    control = c.controls.bind(c.original.operation)
    published = publish_teacher_attempt(c.original, c.deps, control=control)
    allowed = TeacherAttemptView.model_validate_json(
        c.store.read(published.source.allowed_view_ref)
    )
    native = allowed.native
    assert (
        native["steps"] == 1
        and native["generation_rounds"] == 2
        and native["success"] is False
    )
    assert native["attempt_id"] == c.request.scope.attempt_id
    assert ("candidate_id" in native) == v2
    messages = array_value(native["trajectory"], "messages")
    assert len(messages) == 5
    first = object_value(messages[0], "input")
    first_body = object_value(read_json(cast(str, first["content"])), "input body")
    visible = object_value(first_body["actor_visible_input"], "visible binding")
    from lab_generate_skill.domain.actor_prompt import ActorPrompt

    sent = ActorPrompt.model_validate_json(
        c.store.read(c.trace.turns[0].generation.input_ref)
    )
    assert (
        first_body["observation"] == sent.messages[1].content
        and visible["system_message"] == sent.messages[0].content
    )
    invalid = object_value(messages[1], "invalid proposal")
    assert "action_payload" not in invalid and invalid["parsed_decision"] == "invalid"
    actual = object_value(messages[3], "actual action")
    assert actual["action_payload"] == "click('2')"
    result = object_value(actual["operation_result"], "result")
    assert result["status"] == "returned" and result["return_available"] is True
    after = object_value(
        read_json(cast(str, object_value(messages[4], "after")["content"])), "after"
    )
    assert (
        after["last_action_error"] == "original rejected unsaved control"
        and "actor_visible_input" not in after
    )
    assert after["observation_record_source"] == "original_action_return"
    text = allowed.model_dump_json()
    assert all(
        secret not in text
        for secret in (
            "PRIVATE_REFERENCE_ANSWER_NOT_FOR_TEACHER",
            "PRIVATE_NOT_PROJECTED",
            c.evaluation.contract_ref.uri,
        )
    )
    import lab_generate_skill.teacher.actor_attempt as forward

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Readonly cannot call forward composer")

    monkeypatch.setattr(forward, "actor_attempt", forbidden)
    # The review dependency contains no composer, counter, model or browser.
    op = cleanup(c)
    receipt = review_teacher_attempt(
        published, c.review, op, control=c.controls.bind(op)
    )
    assert receipt.source == published.source and c.authority.calls == 2
    assert (
        review_teacher_attempt(published, c.review, op, control=c.controls.bind(op))
        == receipt
    )


@pytest.mark.parametrize(
    "outcome",
    [
        "model_unknown",
        "model_failed",
        "uncertain",
        "not_dispatched",
        "returned_incomplete",
        "empty",
    ],
)
def test_missing_or_incomplete_outcome_stays_unknown_without_invented_return(
    tmp_path: Path, outcome: str
) -> None:
    outcomes = () if outcome == "empty" else (outcome,)
    c = native_attempt_case(
        tmp_path / "case", outcomes=outcomes, evaluation_status="unknown"
    )
    published = publish_teacher_attempt(
        c.original, c.deps, control=c.controls.bind(c.original.operation)
    )
    allowed = TeacherAttemptView.model_validate_json(
        c.store.read(published.source.allowed_view_ref)
    )
    assert allowed.native["success"] is None and allowed.native["reward"] is None
    messages = array_value(allowed.native["trajectory"], "complete diagnostic timeline")
    if outcome == "empty":
        assert len(messages) == 1 and allowed.native["steps"] == 0
        body = object_value(
            read_json(cast(str, object_value(messages[0], "initial")["content"])),
            "initial",
        )
        assert body["observation_record_source"] == "original_initial_observation"
    else:
        action = object_value(messages[1], "response")
        result = object_value(action["operation_result"], "result")
        assert result["result"] is None and result["return_available"] is False
        assert result["status"] == (
            "no_recorded_action"
            if outcome in ("model_unknown", "model_failed")
            else outcome
        )
        assert len(messages) == 2 and allowed.native["steps"] == int(
            outcome == "returned_incomplete"
        )
        before = object_value(
            read_json(cast(str, object_value(messages[0], "before")["content"])),
            "before",
        )
        if outcome in ("model_unknown", "model_failed"):
            assert "actor_visible_input" not in before
            binding = object_value(
                before["recorded_actor_input"], "recorded request only"
            )
            assert (
                binding["delivery"] == "unconfirmed"
                and binding["stage"] == "recorded_generation_input"
            )
        else:
            assert (
                "actor_visible_input" in before and "recorded_actor_input" not in before
            )
        op = cleanup(c)
        review_teacher_attempt(published, c.review, op, control=c.controls.bind(op))

    assert "WITHHELD_PRIVATE" not in allowed.model_dump_json()


@pytest.mark.parametrize(
    "fault",
    ["visible_input", "result", "early_event", "feedback", "identity", "private_extra"],
)
def test_rebound_complete_view_cannot_hide_changed_native_source_fields(
    tmp_path: Path, fault: str
) -> None:
    c = native_attempt_case(tmp_path / "case")
    control = c.controls.bind(c.original.operation)
    published = publish_teacher_attempt(c.original, c.deps, control=control)
    allowed = TeacherAttemptView.model_validate_json(
        c.store.read(published.source.allowed_view_ref)
    )
    native = json.loads(json.dumps(allowed.native))
    if fault == "visible_input":
        original = json.loads(native["trajectory"][0]["content"])
        original["observation"] = "forged visible user message"
        native["trajectory"][0]["content"] = json.dumps(original)
    elif fault == "result":
        native["trajectory"][3]["operation_result"]["status"] = "successful"
    elif fault == "early_event":
        native["trajectory"] = native["trajectory"][2:]
    elif fault == "feedback":
        native["evaluator_feedback"]["checks"][0]["status"] = "pass"
    elif fault == "identity":
        native["attempt_id"] = "other-attempt"
    else:
        native["private_raw_database"] = {"answer": "should never be in allowed view"}
    assert native != allowed.native
    altered = allowed.model_copy(update={"native": native})
    ref = c.store.put(
        altered.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-attempt-input/1",
            visibility="teacher",
            producer="unit-forged-rebound",
        ),
    )
    source = published.source.model_copy(update={"allowed_view_ref": ref})
    receipt = TeacherAttemptReceipt.model_validate_json(
        c.store.read(published.receipt_ref)
    ).model_copy(update={"source": source})
    changed = PublishedTeacherAttempt(receipt_ref=put(c.store, receipt), source=source)
    op = cleanup(c)
    with pytest.raises(EvidenceIntegrityError):
        review_teacher_attempt(changed, c.review, op, control=c.controls.bind(op))


@pytest.mark.parametrize("bad", [None, True, 0, "", [], {}])
def test_wrong_input_contract_refused_before_reads_or_writes(
    tmp_path: Path, bad: object
) -> None:
    c = native_attempt_case(tmp_path / "case")
    with pytest.raises(ValidationError):
        publish_teacher_attempt(
            cast(TeacherAttemptInput, bad),
            c.deps,
            control=c.controls.bind(c.original.operation),
        )
    assert c.authority.calls == 0


@pytest.mark.parametrize(
    "fault",
    ["cancel", "read_timeout", "source_denied", "allowed_ack_loss", "receipt_ack_loss"],
)
def test_cancel_timeout_and_partial_publication_preserve_primary_and_known_refs(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = native_attempt_case(tmp_path / "case")
    control: OperationControl = c.controls.bind(c.original.operation)
    original_read, original_put = c.store.read, c.store.put
    if fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", c.original.operation.operation_id)

            def wait(self, seconds: float) -> None:
                raise AssertionError("No wait")

        control = Cancelled()
    elif fault == "read_timeout":

        def unavailable(ref: EvidenceRef, control: OperationControl) -> bytes:
            if ref == c.original.actor_request_ref:
                raise TimeoutError("Original source read timeout")
            return original_read(ref, control)

        monkeypatch.setattr(c.store, "read", unavailable)
    elif fault == "source_denied":
        c.authority.denied = True
    else:

        def lost(
            raw: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            ref = original_put(raw, metadata, control)
            schema = (
                "teacher-attempt-input/1"
                if fault == "allowed_ack_loss"
                else "teacher-attempt-source-receipt/1"
            )
            if metadata.content_schema == schema:
                raise OSError("Native part committed; ack lost")
            return ref

        monkeypatch.setattr(c.store, "put", lost)
    with pytest.raises(TeacherAttemptUnconfirmed) as saved:
        publish_teacher_attempt(c.original, c.deps, control=control)
    failure = saved.value
    assert failure.primary is failure.__cause__
    if fault == "receipt_ack_loss":
        ref = next(
            r
            for r in failure.retained
            if r.content_schema == "teacher-attempt-source-receipt/1"
        )
        receipt = TeacherAttemptReceipt.model_validate_json(original_read(ref))
        op = cleanup(c)
        assert (
            review_teacher_attempt(
                PublishedTeacherAttempt(receipt_ref=ref, source=receipt.source),
                c.review,
                op,
                control=c.controls.bind(op),
            )
            == receipt
        )
    elif fault == "allowed_ack_loss":
        assert (
            len(failure.retained) == 1
            and failure.retained[0].content_schema == "teacher-attempt-input/1"
        )
        assert original_read(failure.retained[0])
    else:
        assert failure.retained == ()


@pytest.mark.parametrize(
    "fault", ["feedback_missing", "feedback_reorder", "round", "foreign_cleanup"]
)
def test_original_policy_candidate_and_operation_boundaries_are_not_guessed(
    tmp_path: Path, fault: str
) -> None:
    c = native_attempt_case(tmp_path / "case", request_v2=True)
    original = c.original
    if fault.startswith("feedback"):
        names = () if fault == "feedback_missing" else ("different_original_check",)
        original = original.model_copy(
            update={
                "feedback": original.feedback.model_copy(update={"check_names": names})
            }
        )
    elif fault == "round":
        original = original.model_copy(update={"candidate_slot": 4})
    else:
        op = cleanup(c).model_copy(update={"parent_operation_id": "foreign"})
        with pytest.raises(OwnershipConflict):
            read_actor_material(
                original,
                c.store,
                c.deps.observations,
                c.deps.traces,
                op,
                control=c.controls.bind(op),
            )
        return
    with pytest.raises(TeacherAttemptUnconfirmed):
        publish_teacher_attempt(
            original, c.deps, control=c.controls.bind(original.operation)
        )


def test_extreme_dependency_reference_refuses_before_trace_loader_or_large_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = native_attempt_case(tmp_path / "case")
    t = c.trace.turns[0]
    oversized = t.generation.input_ref.model_copy(update={"size_bytes": 300 * 1024**2})
    gen = t.generation.model_copy(update={"input_ref": oversized})
    trace = c.trace.model_copy(
        update={"turns": (t.model_copy(update={"generation": gen}), *c.trace.turns[1:])}
    )
    original = c.original.model_copy(update={"trace_ref": put(c.store, trace)})

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Large graph must be rejected before TraceRecords resolves it"
        )

    monkeypatch.setattr(c.deps.traces, "load", forbidden)
    with pytest.raises(TeacherAttemptUnconfirmed) as saved:
        publish_teacher_attempt(
            original, c.deps, control=c.controls.bind(original.operation)
        )
    assert isinstance(saved.value.primary, ValueError) and "256MiB" in str(
        saved.value.primary
    )
    assert saved.value.retained == ()


def test_published_descriptor_identity_cannot_rebind_a_valid_allowed_view(
    tmp_path: Path,
) -> None:
    c = native_attempt_case(tmp_path / "case")
    published = publish_teacher_attempt(
        c.original, c.deps, control=c.controls.bind(c.original.operation)
    )
    source = published.source.model_copy(
        update={"attempt_id": "other-original-attempt"}
    )
    receipt = TeacherAttemptReceipt.model_validate_json(
        c.store.read(published.receipt_ref)
    ).model_copy(update={"source": source})
    changed = PublishedTeacherAttempt(receipt_ref=put(c.store, receipt), source=source)
    op = cleanup(c)
    with pytest.raises(EvidenceIntegrityError):
        review_teacher_attempt(changed, c.review, op, control=c.controls.bind(op))


def test_repeated_native_publication_is_same_CAS_and_never_new_permission(
    tmp_path: Path,
) -> None:
    c = native_attempt_case(tmp_path / "case")
    control = c.controls.bind(c.original.operation)
    first = publish_teacher_attempt(c.original, c.deps, control=control)
    files = sorted((c.root / "evidence/blobs").iterdir())
    second = publish_teacher_attempt(c.original, c.deps, control=control)
    assert second == first and sorted((c.root / "evidence/blobs").iterdir()) == files
    c.authority.denied = True
    with pytest.raises(TeacherAttemptUnconfirmed) as saved:
        publish_teacher_attempt(c.original, c.deps, control=control)
    assert (
        isinstance(saved.value.primary, PermissionError) and saved.value.retained == ()
    )
