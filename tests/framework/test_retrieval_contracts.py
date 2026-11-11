"""Split/cluster isolation and deterministic complete-batch ranking contracts."""

from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.bank import BankManifest, SkillRecord, SkillSource
from lab_generate_skill.domain.data_scope import SplitManifest, normalized_goal
from lab_generate_skill.domain.identity import Split
from lab_generate_skill.domain.retrieval import (
    RetrievalResult,
    SkillScore,
    eligible_records,
    rank_retrieval,
    validate_retrieval,
)

from retrieval_fixtures import fixture, member, reference


@pytest.mark.parametrize("split", ["train", "dev", "test"])
def test_normal_rank_and_public_sources_for_each_target_split(split: str) -> None:
    data = fixture(target_split=cast(Split, split))
    selected = validate_retrieval(data.result, data.bank, data.split)
    assert [r.skill_id for r in selected] == ["skill-" + str(i) for i in range(6)]
    assert all(s.task.split == "train" for r in selected for s in r.sources)
    assert (
        RetrievalResult.model_validate_json(data.result.model_dump_json())
        == data.result
    )


def test_normalization_preserves_original_nfkc_casefold_whitespace() -> None:
    assert (
        normalized_goal("  ＡＢＣ\nStraße\tX ")
        == normalized_goal("abc STRASSE x")
        == "abc strasse x"
    )


@pytest.mark.parametrize("value", [None, True, 42, "", "  ", []])
def test_empty_or_wrong_goal_type(value: object) -> None:
    with pytest.raises(ValueError):
        normalized_goal(cast(str, value))


@pytest.mark.parametrize("kind", ["alias", "source", "task", "group"])
def test_partition_overlap_rejected(kind: str) -> None:
    first = member("first")
    second = member("second", "test")
    if kind == "alias":
        second = second.model_copy(update={"aliases": first.aliases})
    elif kind == "group":
        second = second.model_copy(update={"goal_group_id": first.goal_group_id})
    else:
        second = second.model_copy(
            update={
                "identity": second.identity.model_copy(
                    update={
                        kind + "_task_id" if kind == "source" else "task_id": getattr(
                            first.identity,
                            "source_task_id" if kind == "source" else "task_id",
                        )
                    }
                )
            }
        )
    with pytest.raises(ValidationError):
        SplitManifest(partition_id="x", members=(first, second))


@pytest.mark.parametrize(
    "field", ["excluded_source_ids", "excluded_skill_ids", "excluded_goal_groups"]
)
def test_scope_excludes_entire_record(field: str) -> None:
    data = fixture()
    record = data.bank.records[0]
    value = {
        "excluded_source_ids": "runtime-0",
        "excluded_skill_ids": record.sources[0].candidate_skill_id,
        "excluded_goal_groups": "group-0",
    }[field]
    scope = data.scope.model_copy(update={field: (value,)})
    assert [
        r.skill_id for r in eligible_records(data.query, scope, data.bank, data.split)
    ] == ["skill-" + str(i) for i in range(1, 8)]


def test_cluster_with_any_excluded_source_removed_not_partially_rewritten() -> None:
    data = fixture()
    a, b, *rest = data.bank.records
    cluster = SkillRecord.model_validate(
        a.model_copy(update={"sources": a.sources + b.sources})
    )
    bank = BankManifest.model_validate(
        data.bank.model_copy(update={"records": (cluster, *rest)})
    )
    scope = data.scope.model_copy(update={"excluded_source_ids": ("runtime-1",)})
    assert [
        r.skill_id for r in eligible_records(data.query, scope, bank, data.split)
    ] == ["skill-" + str(i) for i in range(2, 8)]
    assert len(cluster.sources) == 2


def test_heldout_normalized_goal_excludes_train_source_with_different_group() -> None:
    data = fixture()
    heldout = member("heldout", "test", "  PUBLIC  ＧＯＡＬ 0 ")
    split = SplitManifest(partition_id="unit", members=(*data.split.members, heldout))
    assert "skill-0" not in [
        r.skill_id for r in eligible_records(data.query, data.scope, data.bank, split)
    ]


def test_same_source_goal_group_and_public_goal_excluded() -> None:
    data = fixture()
    source = data.split.members[0]
    query = data.query.model_copy(
        update={"task": source.identity, "literal_goal": source.public_goal}
    )
    assert "skill-0" not in [
        r.skill_id for r in eligible_records(query, data.scope, data.bank, data.split)
    ]


@pytest.mark.parametrize(
    "change",
    [
        "source_split",
        "candidate_id",
        "digest",
        "private_skill",
        "site",
        "duplicate_source",
        "duplicate_record",
        "missing_source",
        "wrong_group",
    ],
)
def test_malformed_or_inconsistent_lineage_rejected(change: str) -> None:
    data = fixture()
    record = data.bank.records[0]
    source = record.sources[0]
    with pytest.raises((ValueError, ValidationError)):
        if change == "source_split":
            SkillSource.model_validate(
                source.model_copy(
                    update={"task": source.task.model_copy(update={"split": "test"})}
                )
            )
        elif change == "candidate_id":
            SkillSource.model_validate(
                source.model_copy(update={"candidate_skill_id": "arbitrary"})
            )
        elif change == "digest":
            SkillRecord.model_validate(
                record.model_copy(update={"content_digest": "0" * 64})
            )
        elif change == "private_skill":
            SkillRecord.model_validate(
                record.model_copy(
                    update={
                        "skill_ref": record.skill_ref.model_copy(
                            update={"visibility": "private"}
                        )
                    }
                )
            )
        elif change == "site":
            SkillRecord.model_validate(
                record.model_copy(
                    update={
                        "sources": (
                            source,
                            data.bank.records[1]
                            .sources[0]
                            .model_copy(
                                update={
                                    "task": source.task.model_copy(
                                        update={"site": "reddit"}
                                    )
                                }
                            ),
                        )
                    }
                )
            )
        elif change == "duplicate_source":
            SkillRecord.model_validate(
                record.model_copy(update={"sources": (source, source)})
            )
        elif change == "duplicate_record":
            BankManifest.model_validate(
                data.bank.model_copy(update={"records": (*data.bank.records, record)})
            )
        else:
            edited = (
                source.model_copy(
                    update={
                        "task": source.task.model_copy(update={"task_id": "absent"})
                    }
                )
                if change == "missing_source"
                else source.model_copy(update={"goal_group_id": "wrong"})
            )
            bank = data.bank.model_copy(
                update={
                    "records": (
                        record.model_copy(update={"sources": (edited,)}),
                        *data.bank.records[1:],
                    )
                }
            )
            eligible_records(data.query, data.scope, bank, data.split)


@pytest.mark.parametrize(
    "kind",
    ["short", "extra", "reordered", "duplicates", "nan", "infinity", "bool", "list"],
)
def test_scores_must_be_finite_and_cover_exact_ordered_batch(kind: str) -> None:
    data = fixture()
    scores = data.result.scores
    if kind == "short":
        scores = scores[:-1]
    elif kind == "extra":
        scores = (*scores, SkillScore(skill_id="extra", score=0.0))
    elif kind == "reordered":
        scores = tuple(reversed(scores))
    elif kind == "duplicates":
        scores = (scores[0],) * len(scores)
    elif kind == "list":
        scores = cast(tuple[SkillScore, ...], list(scores))
    else:
        scores = (
            scores[0].model_copy(
                update={
                    "score": {
                        "nan": float("nan"),
                        "infinity": float("inf"),
                        "bool": True,
                    }[kind]
                }
            ),
            *scores[1:],
        )
    with pytest.raises(ValueError):
        rank_retrieval(
            data.query,
            data.scope,
            data.bank,
            data.split,
            scores,
            data.result.score_evidence_ref,
        )


@pytest.mark.parametrize("count", [0, 5, 6])
def test_empty_and_minimum_bank(count: int) -> None:
    data = fixture()
    bank = data.bank.model_copy(update={"records": data.bank.records[:count]})
    scores = data.result.scores[:count]
    if count < 6:
        with pytest.raises(ValueError):
            rank_retrieval(
                data.query,
                data.scope,
                bank,
                data.split,
                scores,
                data.result.score_evidence_ref,
            )
    else:
        assert (
            len(
                rank_retrieval(
                    data.query,
                    data.scope,
                    bank,
                    data.split,
                    scores,
                    data.result.score_evidence_ref,
                ).hits
            )
            == 6
        )


@pytest.mark.parametrize("k", [6.0, "6", True, 0, 7, None])
def test_top_six_not_coerced(k: object) -> None:
    data = fixture()
    with pytest.raises(ValidationError):
        RetrievalResult.model_validate(data.result.model_copy(update={"k": k}))


@pytest.mark.parametrize("kind", ["rank", "score", "content", "config", "query"])
def test_consumer_rejects_modified_result(kind: str) -> None:
    data = fixture()
    result = data.result
    if kind in ("rank", "score", "content"):
        changes: dict[str, dict[str, object]] = {
            "rank": {"rank": 2},
            "score": {"score": 2.0},
            "content": {"content_digest": "0" * 64},
        }
        change = changes[kind]
        result = result.model_copy(
            update={
                "hits": (result.hits[0].model_copy(update=change), *result.hits[1:])
            }
        )
    elif kind == "config":
        result = result.model_copy(update={"config_ref": reference({"other": True})})
    else:
        result = result.model_copy(
            update={
                "query": result.query.model_copy(update={"literal_goal": "different"})
            }
        )
    with pytest.raises(ValueError):
        validate_retrieval(result, data.bank, data.split)


@pytest.mark.parametrize("members", [(), [], None])
def test_empty_and_invalid_partition_container(members: object) -> None:
    with pytest.raises(ValidationError):
        SplitManifest.model_validate({"partition_id": "unit", "members": members})


def test_duplicate_aliases_rejected() -> None:
    value = member("one")
    with pytest.raises(ValidationError):
        type(value).model_validate(
            value.model_copy(update={"aliases": ("same", "same")})
        )


def test_valid_other_website_record_is_not_retrieved() -> None:
    data = fixture()
    original = data.split.members[7]
    changed = original.model_copy(
        update={"identity": original.identity.model_copy(update={"site": "reddit"})}
    )
    split = data.split.model_copy(
        update={"members": (*data.split.members[:7], changed, *data.split.members[8:])}
    )
    record = data.bank.records[7]
    source = record.sources[0].model_copy(update={"task": changed.identity})
    bank = data.bank.model_copy(
        update={
            "records": (
                *data.bank.records[:7],
                record.model_copy(update={"sources": (source,)}),
            )
        }
    )
    assert [
        r.skill_id for r in eligible_records(data.query, data.scope, bank, split)
    ] == ["skill-" + str(i) for i in range(7)]
