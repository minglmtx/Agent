"""Frozen independent retrieval inputs and actual Generator consumption."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.domain.bank import BankManifest
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    CallPlanned,
    CallCompleted,
)
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceNotFound,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.retrieval import RetrievalResult, ScoringReceipt
from construction_storage_fixtures import fixture, put
from test_construction_journal import snapshot_path
from test_run_journal import command


def test_real_retrieval_and_generator_skills_use_exact_frozen_scope(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    result = RetrievalResult.model_validate_json(
        data.store.read(data.plan.retrieval_ref)
    )
    assert data.plan.schema_version == "construction-plan/3"
    assert result.scope == data.plan.retrieval_scope
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    request = GenerationInput.model_validate_json(data.store.read(event.call.input_ref))
    assert tuple(s.content_digest for s in request.retrieved_skills) == tuple(
        h.content_digest for h in result.hits
    )
    assert len(request.retrieved_skills) == 6
    saved = journal.append(event, progress.revision, event.operation)
    assert data.journal().read(command()) == saved


@pytest.mark.parametrize("field", ["bank_ref", "split_ref"])
def test_from_run_plan_rejects_different_frozen_bank_or_split(
    tmp_path: Path, field: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    run = EvidenceRunPlans(data.store, journal.controls).load(data.plan.run, command())
    schema = "bank-manifest/1" if field == "bank_ref" else "data-split/1"
    scope = data.plan.retrieval_scope.model_copy(
        update={field: put(data.store, {"different": True}, schema)}
    )
    with pytest.raises(OwnershipConflict, match="frozen RunPlan"):
        ConstructionPlan.from_run_plan(
            run,
            data.plan.run,
            data.plan.task.identity.task_id,
            claim_ref=data.plan.claim_ref,
            public_context_ref=data.plan.public_context_ref,
            context_receipt_ref=data.plan.context_receipt_ref,
            retrieval_ref=data.plan.retrieval_ref,
            retrieval_scope=scope,
        )
    assert not snapshot_path(data).exists()


@pytest.mark.parametrize(
    "field", ["excluded_source_ids", "excluded_skill_ids", "excluded_goal_groups"]
)
def test_consumer_uses_plan_exclusions_not_result_supplied_scope(
    tmp_path: Path, field: str
) -> None:
    data = fixture(tmp_path)
    scope = data.plan.retrieval_scope.model_copy(
        update={field: ("explicit-exclusion",)}
    )
    plan = data.plan.model_copy(update={"retrieval_scope": scope})
    assert (
        ConstructionPlan.model_validate_json(plan.model_dump_json()).retrieval_scope
        == scope
    )
    with pytest.raises(OwnershipConflict, match="another query or scope"):
        data.journal(plan=plan).create(plan, command())
    assert not snapshot_path(data).exists()


@pytest.mark.parametrize("fault", ["query", "scope", "legacy"])
def test_result_cannot_choose_its_own_expected_inputs(
    tmp_path: Path, fault: str
) -> None:
    data = fixture(tmp_path)
    result = RetrievalResult.model_validate_json(
        data.store.read(data.plan.retrieval_ref)
    )
    if fault == "query":
        value: object = result.model_copy(
            update={
                "query": result.query.model_copy(
                    update={"literal_goal": "another query"}
                )
            }
        )
    elif fault == "scope":
        value = result.model_copy(
            update={
                "scope": result.scope.model_copy(
                    update={"excluded_skill_ids": ("other",)}
                )
            }
        )
    else:
        value = {
            "context": data.plan.public_context_ref.sha256,
            "split": "train",
            "skills": [],
        }
    plan = data.plan.model_copy(
        update={"retrieval_ref": put(data.store, value, "retrieval-result/1")}
    )
    expected = ValidationError if fault == "legacy" else OwnershipConflict
    with pytest.raises(expected):
        data.journal(plan=plan).create(plan, command())
    assert not snapshot_path(data).exists()


@pytest.mark.parametrize("fault", ["order", "content"])
def test_generator_input_must_preserve_actual_top_six(
    tmp_path: Path, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    request = GenerationInput.model_validate_json(data.store.read(event.call.input_ref))
    skills = (
        tuple(reversed(request.retrieved_skills))
        if fault == "order"
        else (
            request.retrieved_skills[0].model_copy(
                update={"principle": "changed meaning"}
            ),
            *request.retrieved_skills[1:],
        )
    )
    changed = request.model_copy(update={"retrieved_skills": skills})
    event = event.model_copy(
        update={
            "call": event.call.model_copy(
                update={
                    "input_ref": put(
                        data.store, changed, changed.schema_version, "public"
                    )
                }
            )
        }
    )
    before = snapshot_path(data).read_bytes()
    with pytest.raises(OwnershipConflict, match="Generator input"):
        journal.append(event, progress.revision, event.operation)
    assert snapshot_path(data).read_bytes() == before


@pytest.mark.parametrize("stage", ["create", "generator"])
@pytest.mark.parametrize("item", ["scores", "execution", "skill", "review"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_deep_retrieval_evidence_reverified_before_new_work(
    tmp_path: Path, stage: str, item: str, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    event = None
    if stage == "generator":
        progress = journal.create(data.plan, command())
        event = data.event(progress)
    result = RetrievalResult.model_validate_json(
        data.store.read(data.plan.retrieval_ref)
    )
    scores = ScoringReceipt.model_validate_json(
        data.store.read(result.score_evidence_ref)
    )
    bank = BankManifest.model_validate_json(data.store.read(result.scope.bank_ref))
    targets = {
        "scores": result.score_evidence_ref,
        "execution": scores.execution_ref,
        "skill": result.hits[0].skill_ref,
        "review": bank.records[0].sources[0].review_ref,
    }
    path = tmp_path / "evidence" / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    snapshot = snapshot_path(data)
    before = snapshot.read_bytes() if snapshot.exists() else None
    expected = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    with pytest.raises(expected):
        if stage == "create":
            journal.create(data.plan, command())
        else:
            assert event is not None
            journal.append(event, progress.revision, event.operation)
    assert (snapshot.read_bytes() if snapshot.exists() else None) == before


def test_authority_denial_blocks_new_generation_but_preserves_known_response(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    creation = command()
    progress = journal.create(data.plan, creation)
    event = data.event(progress)
    progress = journal.append(event, progress.revision, event.operation)
    data.retrieval_authority.denied = True
    assert journal.create(data.plan, creation) == progress
    assert journal.read(command()) == progress
    assert journal.append(event, -1, event.operation) == progress
    response = data.event(progress)
    assert isinstance(response, CallCompleted)
    progress = journal.append(response, progress.revision, response.operation)
    next_call = data.event(progress)
    assert isinstance(next_call, CallPlanned)
    before = snapshot_path(data).read_bytes()
    with pytest.raises(OwnershipConflict):
        journal.append(next_call, progress.revision, next_call.operation)
    assert snapshot_path(data).read_bytes() == before


@pytest.mark.parametrize("fault", ["list", "empty", "too_many", "wrong_type"])
def test_replacement_port_return_contract_is_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    request = GenerationInput.model_validate_json(data.store.read(event.call.input_ref))
    variants: dict[str, object] = {
        "list": list(request.retrieved_skills),
        "empty": (),
        "too_many": (*request.retrieved_skills, request.retrieved_skills[0]),
        "wrong_type": (None,) * 6,
    }
    monkeypatch.setattr(
        journal.verifier.retrieval.records, "load", lambda *args: variants[fault]
    )
    with pytest.raises(ValueError):
        journal.append(event, progress.revision, event.operation)


@pytest.mark.parametrize("fault", ["legacy", "missing", "invalid"])
def test_construction_scope_is_required_and_versioned(
    tmp_path: Path, fault: str
) -> None:
    data = fixture(tmp_path)
    value = data.plan.model_dump()
    if fault == "legacy":
        value["schema_version"] = "construction-plan/1"
    elif fault == "missing":
        del value["retrieval_scope"]
    else:
        value["retrieval_scope"] = None
    with pytest.raises(ValidationError):
        ConstructionPlan.model_validate(value)
