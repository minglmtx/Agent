from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "2.0"


class Domain(StrEnum):
    GITLAB = "gitlab"
    MAP = "map"
    REDDIT = "reddit"
    SHOPPING = "shopping"
    SHOPPING_ADMIN = "shopping_admin"
    CROSS_DOMAIN = "cross_domain"


class TraceError(BaseModel):
    type: str
    message: str
    stage: str


class TraceMessage(BaseModel):
    turn: int = Field(ge=0)
    role: Literal["system", "user", "assistant"]
    content: str
    action_kind: str | None = None
    action_payload: str | None = None


class TrajectoryRecord(BaseModel):
    """One imported or online browser trajectory with explicit outcome provenance."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    trace_id: str
    domain: Literal["gitlab", "map", "reddit", "shopping", "shopping_admin"]
    task_id: str
    rollout_index: int = Field(ge=0)
    seed: int
    task_instruction: str
    benchmark_skill_tags: list[str] = Field(default_factory=list)
    model: str
    system_prompt: str
    messages: list[TraceMessage] = Field(default_factory=list)
    sample_status: str
    evaluation_outcome: str
    finish_reason: str | None = None
    task_output: dict[str, Any] | None = None
    rounds: int = Field(ge=0)
    started_at: str
    finished_at: str
    generation_finish_reasons: list[str] = Field(default_factory=list)
    error: TraceError | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.evaluation_outcome == "correct"


class SkillStep(BaseModel):
    step: int = Field(ge=1)
    instruction: str = Field(min_length=1)
    action_template: str = Field(min_length=1)
    expected_observation: str = Field(min_length=1)
    recovery: str | None = None


class FailureMode(BaseModel):
    symptom: str = Field(min_length=1)
    likely_cause: str = Field(min_length=1)
    recovery: str = Field(min_length=1)


class CandidateSkill(BaseModel):
    """Extended model-facing skill schema."""

    model_config = ConfigDict(extra="forbid")

    domain: Literal[
        "gitlab", "map", "reddit", "shopping", "shopping_admin", "cross_domain"
    ]
    skill_type: Literal["strategy", "procedure", "verification", "recovery"]
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=20)
    when_to_use: list[str] = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    procedure: list[SkillStep] = Field(min_length=1)
    verification: list[str] = Field(min_length=1)
    failure_modes: list[FailureMode] = Field(default_factory=list)
    transfer_notes: list[str] = Field(default_factory=list)
    benchmark_skill_tags: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(min_length=1)

    @field_validator(
        "when_to_use",
        "prerequisites",
        "verification",
        "transfer_notes",
        "benchmark_skill_tags",
        "source_trace_ids",
    )
    @classmethod
    def strip_string_lists(cls, values: list[str]) -> list[str]:
        return [
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ]

    @field_validator("procedure")
    @classmethod
    def normalize_step_numbers(cls, values: list[SkillStep]) -> list[SkillStep]:
        for index, value in enumerate(values, start=1):
            value.step = index
        return values


class SkillEvidence(BaseModel):
    successful_trace_ids: list[str] = Field(default_factory=list)
    failed_trace_ids: list[str] = Field(default_factory=list)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    source_task_ids: list[str] = Field(default_factory=list)


class QualityAssessment(BaseModel):
    valid: bool
    truncated: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0)


class SkillProvenance(BaseModel):
    generator_backend: str
    generator_model: str
    prompt_version: str
    generated_at: str
    raw_generation_id: str
    merged_raw_generation_ids: list[str] = Field(default_factory=list)


class EmbeddingReference(BaseModel):
    backend: str
    model: str
    dimensions: int = Field(gt=0)
    vector_index: int = Field(ge=0)


class ClusterInfo(BaseModel):
    cluster_id: str
    canonical: bool
    duplicate_of: str | None = None
    similarity_to_canonical: float | None = Field(default=None, ge=-1.0, le=1.0)


class SkillRecord(CandidateSkill):
    skill_id: str
    retrieval_text: str = Field(min_length=1)
    evidence: SkillEvidence
    quality: QualityAssessment
    provenance: SkillProvenance
    embedding: EmbeddingReference | None = None
    cluster: ClusterInfo | None = None


from .skill_budget import (
    _NUMBERED_STEP, numbered_skill_steps, skill_word_count, skill_length_report,
    HARD_WORD_LIMITS, HARD_TOTAL_WORDS, HARD_STEPS,
)

class CompactSkill(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1)
    principle: str = Field(min_length=1)
    when_to_apply: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_content_budget(self):
        counts = {}
        for field, maximum in HARD_WORD_LIMITS.items():
            counts[field] = skill_word_count(getattr(self, field))
            if counts[field] > maximum:
                raise ValueError(f"{field}_word_limit: {counts[field]} > {maximum}")
        if sum(counts.values()) > HARD_TOTAL_WORDS:
            raise ValueError(f"skill_total_word_limit: total exceeds {HARD_TOTAL_WORDS}")
        # Multi-step content uses numbered lines inside the existing string field.
        # Plain prose stays valid; detecting implicit semantic steps is not attempted.
        steps = numbered_skill_steps(self.principle)
        if re.search(r"(?m)^[ \t]*[-*•][ \t]+", self.principle):
            raise ValueError("skill_step_format: use numbered lines for a procedure")
        if steps:
            if len(steps) > HARD_STEPS:
                raise ValueError(f"skill_step_limit: more than {HARD_STEPS} steps")
            if self.principle[:steps[0].start()].strip():
                raise ValueError("skill_step_format: put all procedure text inside the numbered steps")
            if [int(m.group(1)) for m in steps] != list(range(1, len(steps) + 1)):
                raise ValueError("skill_step_format: number steps consecutively from 1")
            for index, step in enumerate(steps):
                end = steps[index + 1].start() if index + 1 < len(steps) else len(self.principle)
                body = self.principle[step.end():end]
                if not body.strip():
                    raise ValueError("skill_step_format: empty step")

        return self


    def length_report(self):
        return skill_length_report(self)


class CompactSkillRecord(CompactSkill):
    skill_id: str
    domain: Literal["gitlab", "map", "reddit", "shopping", "shopping_admin"]
    source_trace_ids: list[str]
    benchmark_skill_tags: list[str] = Field(default_factory=list)
    retrieval_text: str
    evidence: SkillEvidence
    quality: QualityAssessment
    provenance: SkillProvenance
    embedding: EmbeddingReference | None = None
    cluster: ClusterInfo | None = None


class SkillBankMetadata(BaseModel):
    bank_id: str
    created_at: str
    schema_version: str = SCHEMA_VERSION
    domains: list[Literal["gitlab", "map", "reddit", "shopping", "shopping_admin"]] = (
        Field(
            default_factory=lambda: [
                "gitlab",
                "map",
                "reddit",
                "shopping",
                "shopping_admin",
            ]
        )
    )
    source_trajectory_count: int = Field(ge=0)
    validated_candidate_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    canonical_skill_count: int = Field(ge=0)
    duplicate_skill_count: int = Field(ge=0)
    embedding_backend: str
    embedding_model: str
    clustering_threshold: float = Field(ge=-1.0, le=1.0)


class SkillBank(BaseModel):
    metadata: SkillBankMetadata
    skills: list[CompactSkillRecord | SkillRecord]


class RawGenerationEnvelope(BaseModel):
    generation_id: str
    domain: Literal["gitlab", "map", "reddit", "shopping", "shopping_admin"]
    task_id: str
    trace_ids: list[str]
    prompt_version: str
    generator_backend: str
    generator_model: str
    generated_at: str
    finish_reason: str | None
    response_text: str
    parse_error: str | None = None
    attempt: int = 1
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost: float | None = None
    provider_response_id: str | None = None
    api_error_type: str | None = None
    api_error_code: int | None = None
    provider_request_id: str | None = None
    billing_status: str | None = None
    error_diagnostics: dict[str, Any] | None = None
    elapsed_seconds: float | None = None


class RawCandidateEnvelope(BaseModel):
    generation_id: str
    candidate_index: int = Field(ge=0)
    domain: Literal["gitlab", "map", "reddit", "shopping", "shopping_admin"]
    task_id: str
    trace_ids: list[str]
    prompt_version: str
    generator_backend: str
    generator_model: str
    generated_at: str
    finish_reason: str | None
    candidate: dict[str, Any]
    length_check: dict[str, Any] | None = None
