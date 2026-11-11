"""Complete construction source composition; approved parts/authority synthetic.

Actual file history/CAS/public observation/retrieval consumer and common budget
are used; this does not qualify raw trace projection, a real route or a model.
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast
from datetime import datetime, timezone
import pytest
from pydantic import JsonValue, ValidationError
from lab_generate_skill.application.teacher_source import (
    publish_teacher_source,
    TeacherSourceUnconfirmed,
)
from lab_generate_skill.application.teacher_source_review import (
    review_teacher_source,
    TeacherSourceReviewDeps,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_authority
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationDeps,
)
from lab_generate_skill.application.context_review import (
    review_context,
    ContextReviewDeps,
)
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherSourceReceipt,
    PublishedTeacherSource,
)
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    native_evidence,
)
from lab_generate_skill.domain.teacher_json import json_text, array_value, object_value
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.construction import (
    CallPlanned,
    CallUncertain,
    AttemptCompleted,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from context_preparation_fixtures import UnitAuthority
from context_budget_fixtures import profile
from teacher_context_fixtures import (
    teacher_projection_case,
    UnitTeacherCounts,
    UnitTeacherCountReview,
)
from teacher_source_fixtures import source_case, TeacherSourceCase
from source_review_records import ReadOnlyEvidence
from test_run_journal import command


def readonly(
    case: TeacherSourceCase, operation: OperationContext | None = None
) -> TeacherSourceReviewDeps:
    store = ReadOnlyEvidence(case.data.root / "evidence")
    op = operation or case.bindings.operation.cleanup(
        "source-closed-review", now=datetime.now(timezone.utc), seconds=30
    )
    return TeacherSourceReviewDeps(
        store,
        EvidenceObservations(store, case.controls),
        EvidenceRetrievalRecords(store, case.controls, case.data.retrieval_authority),
        case.authority,
        op,
    )


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_complete_original_four_attempts_common_prepare_and_closed_independent_source_review(
    tmp_path: Path, site: Site
) -> None:
    c = source_case(tmp_path / "case", site)
    control = c.controls.bind(c.bindings.operation)
    result = publish_teacher_source(c.progress, c.bindings, c.deps, control=control)
    allowed = AllowedTeacherEvidence.model_validate_json(
        c.data.store.read(result.source.allowed_input_ref)
    )
    body = native_evidence(allowed.messages[1].content)
    assert len(array_value(body["attempts"], "all original attempts")) == 4
    assert allowed.scope.task.site == site and allowed.teacher_round == 1
    assert c.authority.prepares == 1
    original_parts = [
        c.data.store.read(v.allowed_view_ref) for v in c.bindings.attempts
    ]
    r = readonly(c)
    receipt = review_teacher_source(result, r, control=c.controls.bind(r.operation))
    assert receipt.bindings == c.bindings and receipt.source == result.source
    assert not hasattr(r, "compose")
    # Same original source proof is mandatory in preparation and closed count review.
    admitted = teacher_source_authority(
        UnitAuthority(),
        result,
        evidence=c.data.store,
        observations=c.observations,
        retrieval=c.retrieval,
        authority=c.authority,
        operation=c.bindings.operation,
    )
    policy = teacher_projection_case(site).policy
    project, protect = build_teacher_context(policy)
    counter = UnitTeacherCounts(c.data.store)
    request = ContextPreparationRequest(
        schema_version="context-preparation-request/2",
        scope=result.source.scope,
        operation=c.bindings.operation,
        request_id=c.bindings.request_id,
        source=result.source,
        profile=profile(
            "teacher",
            model="unit-teacher-byte-tokens",
            context_window=400017,
            input_limit=400000,
            output_reserve=17,
            soft_target=340000,
        ),
        policy=policy,
    )
    prepared = prepare_context(
        request,
        ContextPreparationDeps(c.data.store, admitted, project, protect, counter),
        control=control,
    )
    assert prepared.outcome == "prepared" and counter.calls == 2
    closed = teacher_source_authority(
        UnitAuthority(),
        result,
        evidence=r.evidence,
        observations=r.observations,
        retrieval=r.retrieval,
        authority=r.authority,
        operation=r.operation,
    )
    count_review = UnitTeacherCountReview(r.evidence)
    final = review_context(
        request,
        prepared,
        ContextReviewDeps(r.evidence, closed, project, protect, count_review),
        expected_input_ref=prepared.selected_input_ref,
        control=c.controls.bind(r.operation),
    )
    assert final.request.source == result.source and counter.calls == 2
    assert [
        c.data.store.read(v.allowed_view_ref) for v in c.bindings.attempts
    ] == original_parts


@pytest.mark.parametrize("round_number", [2, 3])
def test_all_previous_revisions_and_early_events_are_kept_in_original_order(
    tmp_path: Path, round_number: int
) -> None:
    c = source_case(tmp_path / "case", round_number=round_number)
    published = publish_teacher_source(
        c.progress, c.bindings, c.deps, control=c.controls.bind(c.bindings.operation)
    )
    allowed = AllowedTeacherEvidence.model_validate_json(
        c.data.store.read(published.source.allowed_input_ref)
    )
    body = native_evidence(allowed.messages[1].content)
    attempts = array_value(body["attempts"], "all attempts")
    assert len(attempts) == round_number + 3
    assert all(
        len(array_value(object_value(a, "attempt")["trajectory"], "early events")) > 6
        for a in attempts
    )
    assert [object_value(a, "attempt")["skill"] for a in attempts] == [
        v.response.skill.model_payload() for v in c.progress.project().candidates
    ]
    r = readonly(c)
    assert (
        review_teacher_source(
            published, r, control=c.controls.bind(r.operation)
        ).source.teacher_round
        == round_number
    )


def test_bootstrap_success_still_publishes_mandatory_first_teacher_and_original_best(
    tmp_path: Path,
) -> None:
    c = source_case(tmp_path / "case", first_success=True)
    published = publish_teacher_source(
        c.progress, c.bindings, c.deps, control=c.controls.bind(c.bindings.operation)
    )
    body = native_evidence(
        AllowedTeacherEvidence.model_validate_json(
            c.data.store.read(published.source.allowed_input_ref)
        )
        .messages[1]
        .content
    )
    assert body["best_successful_attempt"] is not None
    assert c.progress.project().next_action.kind == "revise"
    assert len(array_value(body["attempts"], "all failures and success")) == 4


@pytest.mark.parametrize(
    "fault",
    [
        "omit",
        "reorder",
        "new_request_after_pending",
        "unknown_attempt",
        "source_denial",
    ],
)
def test_unready_incomplete_reordered_or_denied_sources_refuse_before_any_publication(
    tmp_path: Path, fault: str
) -> None:
    c = source_case(tmp_path / "case")
    progress = c.progress
    bindings = c.bindings
    if fault == "omit":
        # Use round2 to retain the shape's minimum4 while omitting a real member.
        c = source_case(tmp_path / "round2", round_number=2)
        progress = c.progress
        bindings = c.bindings.model_copy(update={"attempts": c.bindings.attempts[:-1]})
    elif fault == "reorder":
        bindings = bindings.model_copy(
            update={"attempts": tuple(reversed(bindings.attempts))}
        )
    elif fault == "new_request_after_pending":
        c.authority.pending = True
        bindings = bindings.model_copy(
            update={"request_id": "another-attempt-format-request"}
        )
    elif fault == "unknown_attempt":
        events = list(progress.events)
        for i in range(len(events) - 1, -1, -1):
            candidate = events[i]
            if isinstance(candidate, AttemptCompleted):
                old = candidate.result
                unknown = old.evaluation.model_copy(
                    update={"status": "unknown", "reward": None, "checks": ()}
                )
                events[i] = candidate.model_copy(
                    update={"result": old.model_copy(update={"evaluation": unknown})}
                )
                break
        progress = progress.model_copy(update={"events": tuple(events)})
    else:
        c.authority.denied = True
    before = set((c.data.root / "evidence/blobs").iterdir())
    with pytest.raises((TeacherSourceUnconfirmed, OwnershipConflict, ValidationError)):
        publish_teacher_source(
            progress, bindings, c.deps, control=c.controls.bind(bindings.operation)
        )
    assert set((c.data.root / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize(
    "fault",
    [
        "early_event",
        "instructions",
        "public_constraint",
        "feedback",
        "best",
        "attempt_order",
    ],
)
def test_independent_review_rejects_rebound_hashes_without_calling_forward_composer(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = source_case(tmp_path / "case")
    published = publish_teacher_source(
        c.progress, c.bindings, c.deps, control=c.controls.bind(c.bindings.operation)
    )
    allowed = AllowedTeacherEvidence.model_validate_json(
        c.data.store.read(published.source.allowed_input_ref)
    )
    body = native_evidence(allowed.messages[1].content)
    attempts = array_value(body["attempts"], "original attempts")
    if fault == "early_event":
        first = object_value(attempts[0], "first attempt")
        first["trajectory"] = array_value(first["trajectory"], "trajectory")[2:]
    elif fault == "instructions":
        allowed = allowed.model_copy(
            update={
                "messages": (
                    allowed.messages[0].model_copy(update={"content": "short summary"}),
                    allowed.messages[1],
                )
            }
        )
    elif fault == "public_constraint":
        public = object_value(body["public_task"], "public task")
        changed_constraint: list[JsonValue] = [
            "Require a different output (unit corruption)"
        ]
        assert public["output_requirements"] != changed_constraint
        public["output_requirements"] = changed_constraint
    elif fault == "feedback":
        object_value(attempts[0], "attempt")["evaluator_feedback"] = {
            "available": False
        }
    elif fault == "best":
        body["best_successful_attempt"] = {"skill": {}, "steps": 0}
    elif fault == "attempt_order":
        body["attempts"] = list(reversed(attempts))
    if fault != "instructions":
        allowed = allowed.model_copy(
            update={
                "messages": (
                    allowed.messages[0],
                    allowed.messages[1].model_copy(update={"content": json_text(body)}),
                )
            }
        )
    source_ref = c.data.store.put(
        allowed.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="unit-rebound-corruption",
        ),
    )
    source = published.source.model_copy(update={"allowed_input_ref": source_ref})
    receipt = TeacherSourceReceipt.model_validate_json(
        c.data.store.read(published.receipt_ref)
    ).model_copy(update={"source": source})
    receipt_ref = c.data.store.put(
        receipt.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-source-receipt/1",
            visibility="private",
            producer="unit-rebound-corruption",
        ),
    )
    changed = PublishedTeacherSource(source=source, receipt_ref=receipt_ref)
    import lab_generate_skill.teacher.construction_messages as forward

    def cannot_compose(*args: object, **kwargs: object) -> None:
        raise AssertionError("Review must not call forward composer")

    monkeypatch.setattr(forward, "construction_messages", cannot_compose)
    r = readonly(c)
    with pytest.raises(EvidenceIntegrityError):
        review_teacher_source(changed, r, control=c.controls.bind(r.operation))


def test_repeated_readonly_source_review_and_publication_are_stable_not_new_permission(
    tmp_path: Path,
) -> None:
    c = source_case(tmp_path / "case")
    first = publish_teacher_source(
        c.progress, c.bindings, c.deps, control=c.controls.bind(c.bindings.operation)
    )
    second = publish_teacher_source(
        c.progress, c.bindings, c.deps, control=c.controls.bind(c.bindings.operation)
    )
    assert first == second
    r = readonly(c)
    one = review_teacher_source(first, r, control=c.controls.bind(r.operation))
    assert review_teacher_source(first, r, control=c.controls.bind(r.operation)) == one
    c.authority.pending = True
    with pytest.raises(TeacherSourceUnconfirmed):
        publish_teacher_source(
            c.progress,
            c.bindings,
            c.deps,
            control=c.controls.bind(c.bindings.operation),
        )
    assert review_teacher_source(first, r, control=c.controls.bind(r.operation)) == one


@pytest.mark.parametrize("bad", [None, {}, [], True, 17, "bindings"])
def test_empty_or_wrong_type_source_bindings_refuse_without_writes(
    tmp_path: Path, bad: object
) -> None:
    c = source_case(tmp_path / "case")
    before = set((c.data.root / "evidence/blobs").iterdir())
    with pytest.raises(ValidationError):
        publish_teacher_source(
            c.progress,
            cast(TeacherSourceBindings, bad),
            c.deps,
            control=c.controls.bind(c.bindings.operation),
        )
    assert set((c.data.root / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize("phase", ["cancel", "read_timeout", "receipt_commit_ack_loss"])
def test_source_cancel_timeout_and_partial_publish_preserve_primary_and_known_refs(
    tmp_path: Path, phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.errors import OperationStopped

    c = source_case(tmp_path / "case")
    control: OperationControl = c.controls.bind(c.bindings.operation)
    store = c.data.store
    real_read, real_put = store.read, store.put
    if phase == "cancel":

        class Stopped:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", c.bindings.operation.operation_id)

            def wait(self, seconds: float) -> None:
                raise AssertionError("No wait")

        control = Stopped()
    elif phase == "read_timeout":

        def unavailable(reference: EvidenceRef, control: OperationControl) -> bytes:
            if reference == c.bindings.attempts[0].allowed_view_ref:
                raise TimeoutError("Original approved view read timed out")
            return real_read(reference, control)

        monkeypatch.setattr(store, "read", unavailable)
    else:

        def lost(
            data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            result = real_put(data, metadata, control)
            if metadata.content_schema == "teacher-source-receipt/1":
                raise OSError("Source receipt committed but acknowledgement lost")
            return result

        monkeypatch.setattr(store, "put", lost)
    with pytest.raises(TeacherSourceUnconfirmed) as saved:
        publish_teacher_source(c.progress, c.bindings, c.deps, control=control)
    failure = saved.value
    assert failure.primary is failure.__cause__
    if phase == "receipt_commit_ack_loss":
        receipt_ref = next(
            r
            for r in failure.retained
            if r.content_schema == "teacher-source-receipt/1"
        )
        receipt = TeacherSourceReceipt.model_validate_json(
            real_read(receipt_ref, c.controls.bind(c.bindings.operation))
        )
        known = PublishedTeacherSource(receipt_ref=receipt_ref, source=receipt.source)
        r = readonly(c)
        assert (
            review_teacher_source(known, r, control=c.controls.bind(r.operation))
            == receipt
        )
    else:
        assert failure.retained == ()
