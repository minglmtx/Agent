"""Common orchestration only: synthetic role sources and explicit authority."""

from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationUnconfirmed,
)
from lab_generate_skill.application.context_review import review_context
from lab_generate_skill.domain.context_budget import ContextRole
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextPreparationReceipt,
    ContextInputDraft,
)
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
)
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.ports.lifecycle import OperationControl
from context_preparation_fixtures import preparation_case
from test_slurm_commands import guard


@pytest.mark.parametrize("role", ["actor", "teacher"])
@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_common_role_site_noop_budget_publication_and_readonly_preparation_review(
    tmp_path: Path, role: ContextRole, site: Site
) -> None:
    case = preparation_case(tmp_path, role, site)
    control = guard()
    prepared = prepare_context(case.request, case.deps(), control=control)
    assert prepared.outcome == "prepared" and prepared.selected_input_ref is not None
    calls = case.counter.calls
    receipt = review_context(
        case.request,
        prepared,
        case.review_deps(),
        expected_input_ref=prepared.selected_input_ref,
        control=control,
    )
    assert (
        receipt.request == case.request
        and case.counter.calls == calls == 1
        and case.counter.reviews == 1
    )
    assert case.authority.calls == case.authority.reviews == 1
    repeated = prepare_context(case.request, case.deps(), control=control)
    assert repeated == prepared  # Idempotent CAS only; never sends a model request.


@pytest.mark.parametrize(
    "tokens,outcome",
    [
        (1, "prepared"),
        (80, "prepared"),
        (81, "prepared"),
        (100, "prepared"),
        (101, "budget_rejected"),
    ],
)
def test_soft_hard_boundaries_keep_full_bytes_and_refuse_without_effective_failure(
    tmp_path: Path, tokens: int, outcome: str
) -> None:
    case = preparation_case(tmp_path, tokens=tokens)
    result = prepare_context(case.request, case.deps(), control=guard())
    assert result.outcome == outcome
    receipt = review_context(
        case.request,
        result,
        case.review_deps(),
        expected_input_ref=result.selected_input_ref,
        control=guard(),
    )
    assert receipt.counts[0].measurement.input_tokens == tokens
    assert b"x" * (tokens - 1) in case.evidence.read(receipt.drafts[0].input_ref)
    assert (result.selected_input_ref is None) == (outcome == "budget_rejected")


@pytest.mark.parametrize("status", ["fail", "unknown"])
def test_protection_refusal_is_saved_before_any_count(
    tmp_path: Path, status: str
) -> None:
    case = preparation_case(tmp_path, two_formats=True)
    case.protection.status = status
    result = prepare_context(case.request, case.deps(), control=guard())
    receipt = review_context(
        case.request,
        result,
        case.review_deps(),
        expected_input_ref=None,
        control=guard(),
    )
    assert (
        result.outcome == "integrity_rejected"
        and receipt.decision is None
        and receipt.counts == ()
    )
    assert len(receipt.drafts) == 2 and case.counter.calls == case.counter.reviews == 0


def test_unknown_request_denied_before_effects_even_if_id_changes(
    tmp_path: Path,
) -> None:
    case = preparation_case(tmp_path)
    case.authority.pending = True
    for identity in ("original-request", "changed-request"):
        request = ContextPreparationRequest.model_validate(
            {**case.request.model_dump(), "request_id": identity}
        )
        with pytest.raises(ContextPreparationUnconfirmed) as caught:
            prepare_context(request, case.deps(), control=guard())
        assert caught.value.phase == "authority" and caught.value.retained == ()
        assert isinstance(caught.value.primary, PermissionError)
    assert case.counter.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", ""),
        ("request_id", None),
        ("profile", None),
        ("policy", None),
        ("source", None),
        ("schema_version", "context-preparation-request/2"),
        ("extra", 1),
    ],
)
def test_request_rejects_missing_empty_wrong_type_and_version(
    tmp_path: Path, field: str, value: object
) -> None:
    case = preparation_case(tmp_path)
    with pytest.raises(ValidationError):
        ContextPreparationRequest.model_validate(
            {**case.request.model_dump(), field: value}
        )
    assert case.counter.calls == 0


@pytest.mark.parametrize("stage", [1, 2, 4])
@pytest.mark.parametrize("fault", ["lost", "cancel", "foreign"])
def test_uncertain_input_or_final_receipt_commit_retains_refs_without_recount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: int, fault: str
) -> None:
    case = preparation_case(tmp_path)
    original = case.evidence.put
    writes = 0

    def put(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        nonlocal writes
        writes += 1
        result = original(data, metadata, control, exchange_id=exchange_id)
        if writes == stage:
            if fault == "lost":
                raise OSError("context write acknowledgement lost")
            if fault == "cancel":
                raise OperationStopped("CANCELLED", "context-publication")
            return result.model_copy(update={"sha256": "0" * 64})
        return result

    monkeypatch.setattr(case.evidence, "put", put)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    error = caught.value
    assert error.phase == ("save_inputs" if stage <= 2 else "save_receipt")
    assert len(error.retained) >= stage
    assert case.counter.calls == (0 if stage <= 2 else 1) and writes == stage
    if stage == 4 and fault == "lost":
        fact = ContextPreparationReceipt.model_validate_json(
            case.evidence.read(error.retained[-1])
        )
        assert (
            fact.request.request_id == "original-request" and fact.outcome == "prepared"
        )


@pytest.mark.parametrize("fault", ["cancel", "timeout", "wrong-bytes"])
def test_read_failure_preserves_stage_and_has_no_counter_or_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = preparation_case(tmp_path)

    def read(reference: EvidenceRef, control: OperationControl) -> bytes:
        if fault == "wrong-bytes":
            return b"{}"
        raise OperationStopped(fault.upper(), "context-source")

    monkeypatch.setattr(case.evidence, "read", read)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    assert (
        caught.value.phase == "source"
        and caught.value.retained == ()
        and case.counter.calls == 0
    )


def test_review_rejects_different_selected_input_and_never_counts(
    tmp_path: Path,
) -> None:
    case = preparation_case(tmp_path)
    result = prepare_context(case.request, case.deps(), control=guard())
    with pytest.raises(EvidenceIntegrityError):
        review_context(
            case.request,
            result,
            case.review_deps(),
            expected_input_ref=case.request.source.original_ref,
            control=guard(),
        )
    assert case.counter.calls == 1 and case.counter.reviews == 0


@pytest.mark.parametrize("fault", ["empty", "list", "duplicate", "policy", "source"])
def test_malformed_projection_is_rejected_before_saving_or_counting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = preparation_case(tmp_path, two_formats=True)
    original = case.projector.project

    def project(
        source: AllowedContextSource, raw: bytes, policy: ContextProjectionPolicy
    ) -> tuple[ContextInputDraft, ...]:
        drafts = original(source, raw, policy)
        if fault == "empty":
            return ()
        if fault == "list":
            return cast(tuple[ContextInputDraft, ...], list(drafts))
        if fault == "duplicate":
            return (drafts[0], drafts[0])
        if fault == "policy":
            return (drafts[0].model_copy(update={"policy_sha256": "0" * 64}), drafts[1])
        foreign = source.model_copy(
            update={"scope": source.scope.model_copy(update={"context_id": "other"})}
        )
        return (drafts[0].model_copy(update={"source": foreign}), drafts[1])

    monkeypatch.setattr(case.projector, "project", project)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    assert (
        caught.value.phase == "projection"
        and caught.value.retained == ()
        and case.counter.calls == 0
    )


@pytest.mark.parametrize("fault", ["omitted", "duplicate", "list"])
def test_incomplete_or_wrong_type_protection_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = preparation_case(tmp_path)
    original = case.protection.verify

    def verify(
        source: AllowedContextSource,
        raw: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        checks = original(source, raw, draft, policy)
        if fault == "omitted":
            return checks[:-1]
        if fault == "duplicate":
            return (checks[0], checks[0])
        return cast(tuple[ContextProtectionCheck, ...], list(checks))

    monkeypatch.setattr(case.protection, "verify", verify)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    assert (
        caught.value.phase == "protection"
        and caught.value.retained == ()
        and case.counter.calls == 0
    )


def test_partial_count_keeps_prior_count_evidence_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = preparation_case(tmp_path, two_formats=True)
    original = case.counter.measure
    calls = 0

    def measure(
        reference: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationStopped("CANCELLED", "second-count")
        return original(reference, profile, policy, control=control)

    monkeypatch.setattr(case.counter, "measure", measure)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    assert caught.value.phase == "count" and calls == 2 and case.counter.calls == 1
    assert (
        len(caught.value.retained) == 5
        and caught.value.retained[-1].content_schema
        == "actor-context-count-execution/1"
    )


def test_foreign_measurement_policy_is_rejected_before_preparation_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = preparation_case(tmp_path)
    original = case.counter.measure

    def measure(
        reference: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        counted = original(reference, profile, policy, control=control)
        return counted.model_copy(
            update={
                "measurement": counted.measurement.model_copy(
                    update={"policy_sha256": "0" * 64}
                )
            }
        )

    monkeypatch.setattr(case.counter, "measure", measure)
    with pytest.raises(ContextPreparationUnconfirmed) as caught:
        prepare_context(case.request, case.deps(), control=guard())
    assert caught.value.phase == "count" and isinstance(
        caught.value.primary, EvidenceIntegrityError
    )
    assert len(caught.value.retained) == 3 and case.counter.calls == 1
