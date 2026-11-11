"""Skill bank content and complete cluster lineage; no training-target labels.

Offline trajectory skills can be retrieval references without being SFT targets.
All contributing members remain present, including excluded candidate IDs.
Actual trace/review/release bytes and provenance require a trusted publisher.
"""

import hashlib
from typing import Literal, Self

from pydantic import Field, model_validator

from .evidence import EvidenceRef
from .identity import TaskIdentity
from .skill import CompactSkill
from .validation import Contract, Identifier, Sha256


class SkillSource(Contract):
    task: TaskIdentity
    goal_group_id: Identifier
    generation_id: Identifier
    candidate_skill_id: Identifier
    trajectory_ref: EvidenceRef
    review_ref: EvidenceRef

    @model_validator(mode="after")
    def training_lineage(self) -> Self:
        if (
            self.candidate_skill_id
            != "candidate_"
            + hashlib.sha256(self.generation_id.encode()).hexdigest()[:20]
        ):
            raise ValueError("Candidate ID must preserve original generation identity")
        if self.task.split != "train":
            raise ValueError("Bank source must be train")
        if (
            self.trajectory_ref.visibility != "private"
            or self.review_ref.visibility != "private"
        ):
            raise ValueError("Source traces and reviews remain private")
        return self


class SkillRecord(Contract):
    schema_version: Literal["skill-record/1"] = "skill-record/1"
    skill_id: Identifier
    skill: CompactSkill
    skill_ref: EvidenceRef
    content_digest: Sha256
    sources: tuple[SkillSource, ...] = Field(min_length=1)
    build_release_ref: EvidenceRef

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.skill_ref.content_schema != "compact-skill/1"
            or self.skill_ref.visibility != "public"
        ):
            raise ValueError("Skill payload must be public compact-skill/1")
        if self.content_digest != self.skill.content_digest:
            raise ValueError("Skill content digest mismatch")
        if self.build_release_ref.visibility != "private":
            raise ValueError("Build release remains private")
        if len({s.task.site for s in self.sources}) != 1:
            raise ValueError("Cluster sources must share one website")
        if len({s.generation_id for s in self.sources}) != len(self.sources) or len(
            {s.candidate_skill_id for s in self.sources}
        ) != len(self.sources):
            raise ValueError("Cluster candidate lineage must be unique")
        return self


class BankManifest(Contract):
    schema_version: Literal["bank-manifest/1"] = "bank-manifest/1"
    bank_id: Identifier
    split_ref: EvidenceRef
    encoder_ref: EvidenceRef
    tokenizer_ref: EvidenceRef
    index_ref: EvidenceRef
    retrieval_config_ref: EvidenceRef
    records: tuple[SkillRecord, ...]

    @model_validator(mode="after")
    def unique_bank(self) -> Self:
        if (
            self.split_ref.content_schema != "data-split/1"
            or self.split_ref.visibility != "private"
        ):
            raise ValueError("Bank requires private data-split/1")
        if any(
            r.visibility != "private"
            for r in (
                self.encoder_ref,
                self.tokenizer_ref,
                self.index_ref,
                self.retrieval_config_ref,
            )
        ):
            raise ValueError("Bank implementation artifacts remain private")
        for reference, schema in (
            (self.encoder_ref, "encoder-files/1"),
            (self.tokenizer_ref, "encoder-files/1"),
            (self.index_ref, "retrieval-index/1"),
            (self.retrieval_config_ref, "encoder-config/1"),
        ):
            if reference.content_schema != schema:
                raise ValueError("Bank artifact has unsupported payload schema")
        if self.tokenizer_ref != self.encoder_ref:
            raise ValueError(
                "MiniLM tokenizer must use the same complete model-file manifest"
            )
        ids = [r.skill_id for r in self.records]
        members = [s.candidate_skill_id for r in self.records for s in r.sources]
        generations = [s.generation_id for r in self.records for s in r.sources]
        if (
            len(set(ids)) != len(ids)
            or len(set(members)) != len(members)
            or len(set(generations)) != len(generations)
        ):
            raise ValueError("Bank IDs or cluster membership overlap")
        owners = {
            s.candidate_skill_id: r.skill_id for r in self.records for s in r.sources
        }
        if any(skill_id in owners and owners[skill_id] != skill_id for skill_id in ids):
            raise ValueError("Representative aliases another cluster member")
        return self
