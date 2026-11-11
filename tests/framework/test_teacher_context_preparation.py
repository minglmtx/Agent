"""Real allowed Teacher layout/CAS/budget/review; fake complete-wire counter only."""

from pathlib import Path
from dataclasses import replace
import pytest
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationUnconfirmed,
)
from lab_generate_skill.application.context_review import (
    review_context,
    ContextReviewDeps,
)
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from source_review_records import ReadOnlyEvidence
from teacher_context_fixtures import (
    teacher_preparation_case,
    UnitTeacherCounts,
    UnitTeacherCountReview,
)
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
@pytest.mark.parametrize("long", [False, True])
def test_actual_teacher_source_layout_budget_saving_and_closed_readonly_view(
    site: Site, long: bool, tmp_path: Path
) -> None:
    c = teacher_preparation_case(
        tmp_path / "source", site, repeated_page_bytes=400 if long else 0
    )
    result = prepare_context(c.request, c.deps(), control=guard())
    assert result.outcome == "prepared" and result.selected_input_ref is not None
    receipt = ContextPreparationReceipt.model_validate_json(
        c.store.read(result.reference)
    )
    assert receipt.decision is not None
    selected = next(
        d for d in receipt.drafts if d.input_ref == result.selected_input_ref
    )
    assert selected.kind == ("exact_body_sharing" if long else "identity")
    assert c.counter.calls == 2
    count = c.counter.calls
    readonly = ReadOnlyEvidence(tmp_path / "source")
    project, protect = build_teacher_context(c.request.policy)
    verifier = UnitTeacherCountReview(readonly)
    verified = review_context(
        c.request,
        result,
        ContextReviewDeps(readonly, c.authority, project, protect, verifier),
        expected_input_ref=result.selected_input_ref,
        control=guard(),
    )
    assert (
        verified == receipt
        and c.counter.calls == count
        and not hasattr(verifier, "measure")
        and verifier.reviews == 2
    )
    assert c.store.read(c.original.source.allowed_input_ref) == c.original.raw


def test_repeated_preparation_is_only_same_CAS_never_permission_and_unknown_blocks_new_ID_format(
    tmp_path: Path,
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    first = prepare_context(c.request, c.deps(), control=guard())
    second = prepare_context(c.request, c.deps(), control=guard())
    assert first == second
    c.authority.pending = True
    calls = c.counter.calls
    changed = c.request.model_copy(
        update={
            "request_id": "another-id",
            "policy": c.request.policy.model_copy(
                update={"forced_kind": "exact_body_sharing"}
            ),
        }
    )
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(changed, c.deps(), control=guard())
    assert caught.value.phase == "authority" and c.counter.calls == calls


@pytest.mark.parametrize("boundary", [-1, 0, 1])
def test_teacher_complete_wire_hard_boundary_refuses_without_effective_failure(
    tmp_path: Path, boundary: int
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    original = prepare_context(c.request, c.deps(), control=guard())
    receipt = ContextPreparationReceipt.model_validate_json(
        c.store.read(original.reference)
    )
    tokens = receipt.counts[0].measurement.input_tokens
    hard = tokens + boundary
    policy = c.request.policy.model_copy(update={"forced_kind": "identity"})
    profile = c.request.profile.model_copy(
        update={"input_limit": hard, "context_window": hard + 17, "soft_target": hard}
    )
    request = c.request.model_copy(update={"profile": profile, "policy": policy})
    # Same immutable policy must be reassembled explicitly; never mutate a
    # previously frozen projector to send a changed-format pending request.
    project, protect = build_teacher_context(policy)
    deps = replace(c.deps(), projector=project, protection=protect)
    result = prepare_context(request, deps, control=guard())
    assert result.outcome == ("budget_rejected" if boundary < 0 else "prepared")
    assert (result.selected_input_ref is None) == (boundary < 0)
    verified = review_context(
        request,
        result,
        replace(c.review_deps(), projector=project, protection=protect),
        expected_input_ref=result.selected_input_ref,
        control=guard(),
    )
    assert verified.counts[0].measurement.input_tokens == tokens
    assert verified.request.profile.output_reserve == 17


def test_counter_partial_failure_preserves_first_original_proof_and_all_inputs(
    tmp_path: Path,
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    c.counter.fail_after = 2
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(c.request, c.deps(), control=guard())
    error = caught.value
    assert error.phase == "count" and isinstance(error.primary, TimeoutError)
    schemas = [r.content_schema for r in error.retained]
    assert schemas.count("teacher-context-count-execution/1") == 1
    assert schemas.count("teacher-model-input/1") == 2
    assert schemas.count("context-transform-audit/1") == 2
    assert c.counter.calls == 2


def test_cancellation_refuses_before_authority_projection_or_counter(
    tmp_path: Path,
) -> None:
    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-teacher")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    c = teacher_preparation_case(tmp_path / "source")
    control: OperationControl = Cancelled()
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(c.request, c.deps(), control=control)
    assert isinstance(caught.value.primary, OperationStopped)
    assert c.counter.calls == c.authority.calls == 0 and caught.value.retained == ()
