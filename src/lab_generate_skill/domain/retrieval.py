"""Exact eligible-list and top-six contracts, independent of encoder execution.

Scores cover the entire ordered eligible list; cached vectors for a different
batch are not interchangeable. Consumers recompute eligibility and ordering.
This verifies bindings and arithmetic, not provenance or truthful model scores.
"""

from typing import Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from .bank import BankManifest, SkillRecord
from .data_scope import SplitManifest, normalized_goal
from .evidence import EvidenceRef
from .identity import TaskIdentity
from .validation import Contract, Identifier, NonEmptyText, Sha256


class RetrievalQuery(Contract):
    task: TaskIdentity
    literal_goal: NonEmptyText
    public_context_ref: EvidenceRef

    @model_validator(mode="after")
    def public_context(self) -> Self:
        if (
            self.public_context_ref.visibility != "public"
            or self.public_context_ref.content_schema != "public-construction-context/1"
        ):
            raise ValueError("Retrieval requires frozen public construction context")
        return self


class RetrievalScope(Contract):
    bank_ref: EvidenceRef
    split_ref: EvidenceRef
    excluded_source_ids: tuple[Identifier, ...] = ()
    excluded_skill_ids: tuple[Identifier, ...] = ()
    excluded_goal_groups: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def explicit_scope(self) -> Self:
        for ref, schema in (
            (self.bank_ref, "bank-manifest/1"),
            (self.split_ref, "data-split/1"),
        ):
            if ref.content_schema != schema or ref.visibility != "private":
                raise ValueError("Invalid bank/split reference")
        for values in (
            self.excluded_source_ids,
            self.excluded_skill_ids,
            self.excluded_goal_groups,
        ):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate exclusion")
        return self


class SkillScore(Contract):
    skill_id: Identifier
    score: float = Field(allow_inf_nan=False)


class RetrievalHit(Contract):
    rank: int = Field(ge=1, le=6)
    skill_id: Identifier
    skill_ref: EvidenceRef
    content_digest: Sha256
    score: float = Field(allow_inf_nan=False)


class ScoringReceipt(Contract):
    schema_version: Literal["retrieval-scores/1"] = "retrieval-scores/1"
    query: RetrievalQuery
    scope: RetrievalScope
    encoder_ref: EvidenceRef
    tokenizer_ref: EvidenceRef
    index_ref: EvidenceRef
    config_ref: EvidenceRef
    scores: tuple[SkillScore, ...] = Field(min_length=6)
    execution_ref: EvidenceRef

    @model_validator(mode="after")
    def private_artifacts(self) -> Self:
        if self.execution_ref.content_schema != "retrieval-execution/1":
            raise ValueError("Scoring requires typed retrieval execution evidence")
        if any(
            ref.visibility != "private"
            for ref in (
                self.encoder_ref,
                self.tokenizer_ref,
                self.index_ref,
                self.config_ref,
                self.execution_ref,
            )
        ):
            raise ValueError(
                "Scoring implementation and execution evidence remain private"
            )
        if len({s.skill_id for s in self.scores}) != len(self.scores):
            raise ValueError("Duplicate scoring row")
        return self


class RetrievalResult(Contract):
    schema_version: Literal["retrieval-result/1"] = "retrieval-result/1"
    query: RetrievalQuery
    scope: RetrievalScope
    method: Literal["minilm-cpu-full-eligible-v1"] = "minilm-cpu-full-eligible-v1"
    config_ref: EvidenceRef
    score_evidence_ref: EvidenceRef
    k: Literal[6] = 6
    scores: tuple[SkillScore, ...] = Field(min_length=6)
    hits: tuple[RetrievalHit, ...] = Field(min_length=6, max_length=6)

    @field_validator("k", mode="before")
    @classmethod
    def exact_k(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("k must be exact integer six")
        return value

    @model_validator(mode="after")
    def ranked(self) -> Self:
        if (
            self.config_ref.visibility != "private"
            or self.score_evidence_ref.visibility != "private"
        ):
            raise ValueError("Scoring evidence stays private")
        if self.score_evidence_ref.content_schema != "retrieval-scores/1":
            raise ValueError("Missing versioned scoring receipt")
        if len({s.skill_id for s in self.scores}) != len(self.scores):
            raise ValueError("Duplicate score")
        expected = sorted(self.scores, key=lambda s: (-s.score, s.skill_id))[:6]
        if [(h.rank, h.skill_id, h.score) for h in self.hits] != [
            (i, s.skill_id, s.score) for i, s in enumerate(expected, 1)
        ]:
            raise ValueError("Hits differ from stable top-six score order")
        if any(
            h.skill_ref.visibility != "public"
            or h.skill_ref.content_schema != "compact-skill/1"
            for h in self.hits
        ):
            raise ValueError("Hit must reference public skill content")
        return self


def eligible_records(
    query: RetrievalQuery,
    scope: RetrievalScope,
    bank: BankManifest,
    split: SplitManifest,
) -> tuple[SkillRecord, ...]:
    query = RetrievalQuery.model_validate(query)
    scope = RetrievalScope.model_validate(scope)
    bank = BankManifest.model_validate(bank)
    split = SplitManifest.model_validate(split)
    if bank.split_ref != scope.split_ref:
        raise ValueError("Bank and retrieval use different partitions")
    target = split.member(query.task)
    if query.literal_goal != target.public_goal:
        raise ValueError("Query must be the exact public goal")
    blocked = set(scope.excluded_source_ids) | set(target.source_ids)
    groups = set(scope.excluded_goal_groups) | {target.goal_group_id}
    heldout = {
        (m.identity.site, normalized_goal(m.public_goal))
        for m in split.members
        if m.identity.split != "train"
    }
    heldout.add((query.task.site, normalized_goal(query.literal_goal)))
    eligible = []
    for record in bank.records:
        remove = bool(
            ({record.skill_id} | {s.candidate_skill_id for s in record.sources})
            & set(scope.excluded_skill_ids)
        )
        for source in record.sources:
            member = split.member(source.task)
            if member.goal_group_id != source.goal_group_id:
                raise ValueError("Source goal group differs from partition")
            remove = (
                remove
                or bool(member.source_ids & blocked)
                or member.goal_group_id in groups
                or (member.identity.site, normalized_goal(member.public_goal))
                in heldout
            )
        if not remove and record.sources[0].task.site == query.task.site:
            eligible.append(record)
    return tuple(eligible)


def rank_retrieval(
    query: RetrievalQuery,
    scope: RetrievalScope,
    bank: BankManifest,
    split: SplitManifest,
    scores: tuple[SkillScore, ...],
    score_evidence_ref: EvidenceRef,
) -> RetrievalResult:
    records = eligible_records(query, scope, bank, split)
    checked: tuple[SkillScore, ...] = TypeAdapter(
        tuple[SkillScore, ...]
    ).validate_python(scores, strict=True)
    if len(records) < 6 or tuple(s.skill_id for s in checked) != tuple(
        r.skill_id for r in records
    ):
        raise ValueError(
            "Scores must cover the entire ordered eligible list of at least six skills"
        )
    by_id = {r.skill_id: r for r in records}
    hits = tuple(
        RetrievalHit(
            rank=i,
            skill_id=s.skill_id,
            skill_ref=by_id[s.skill_id].skill_ref,
            content_digest=by_id[s.skill_id].content_digest,
            score=s.score,
        )
        for i, s in enumerate(
            sorted(checked, key=lambda s: (-s.score, s.skill_id))[:6], 1
        )
    )
    return RetrievalResult(
        query=query,
        scope=scope,
        config_ref=bank.retrieval_config_ref,
        score_evidence_ref=score_evidence_ref,
        scores=checked,
        hits=hits,
    )


def validate_retrieval(
    result: RetrievalResult, bank: BankManifest, split: SplitManifest
) -> tuple[SkillRecord, ...]:
    result = RetrievalResult.model_validate(result)
    expected = rank_retrieval(
        result.query,
        result.scope,
        bank,
        split,
        result.scores,
        result.score_evidence_ref,
    )
    if expected != result:
        raise ValueError("Retrieval changed bank content, configuration or ranking")
    by_id = {r.skill_id: r for r in bank.records}
    return tuple(by_id[h.skill_id] for h in result.hits)


class RetrievalCommitUnconfirmed(RuntimeError):
    """Known encoded bytes survived; reconcile metadata without calling encoder.

    The scoring receipt might already be published. Original failure is the cause.
    This exception is only issued after a store returned the encoded evidence ref.
    """

    reason_code = "RETRIEVAL_COMMIT_UNCONFIRMED"

    def __init__(self, execution_ref: EvidenceRef) -> None:
        self.execution_ref = execution_ref
        super().__init__("Saved encoded evidence requires metadata reconciliation")
