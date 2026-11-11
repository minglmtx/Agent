from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from .clustering import cluster_and_deduplicate
from .config import Settings
from .embeddings import Embedder, create_embedder
from .io_utils import atomic_save_numpy, atomic_write_json, iter_jsonl
from .schemas import (
    CandidateSkill,
    CompactSkill,
    CompactSkillRecord,
    EmbeddingReference,
    QualityAssessment,
    RawCandidateEnvelope,
    SkillBank,
    SkillBankMetadata,
    SkillEvidence,
    SkillProvenance,
    SkillRecord,
    TrajectoryRecord,
)


REQUIRED_CANDIDATE_FIELDS = {
    "domain",
    "skill_type",
    "title",
    "description",
    "when_to_use",
    "prerequisites",
    "procedure",
    "verification",
    "failure_modes",
    "transfer_notes",
    "benchmark_skill_tags",
    "source_trace_ids",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_traces(settings: Settings) -> dict[str, TrajectoryRecord]:
    traces: dict[str, TrajectoryRecord] = {}
    for domain in settings.collection.domains:
        path = settings.paths.trajectories_dir / f"{domain}.jsonl"
        for raw in iter_jsonl(path):
            trace = TrajectoryRecord.model_validate(raw)
            if trace.trace_id in traces:
                raise ValueError(f"Duplicate trace_id: {trace.trace_id}")
            traces[trace.trace_id] = trace
    return traces


def _missing_fields_from_validation(exc: ValidationError) -> list[str]:
    missing: list[str] = []
    for error in exc.errors():
        if error.get("type") == "missing" and error.get("loc"):
            missing.append(str(error["loc"][0]))
    return sorted(set(missing))


def _contains_truncated_text(value: Any) -> bool:
    if isinstance(value, str):
        stripped = value.rstrip()
        return stripped.endswith(("...", "…", "[TRUNCATED]")) or stripped.count("```") % 2 == 1
    if isinstance(value, list):
        return any(_contains_truncated_text(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_truncated_text(item) for item in value.values())
    return False


def _retrieval_text(candidate: CandidateSkill) -> str:
    parts = [
        f"domain: {candidate.domain}",
        f"type: {candidate.skill_type}",
        candidate.title,
        candidate.description,
        "triggers: " + "; ".join(candidate.when_to_use),
        "procedure: "
        + " ".join(
            f"{step.instruction} {step.action_template} {step.expected_observation}"
            for step in candidate.procedure
        ),
        "verification: " + "; ".join(candidate.verification),
        "tags: " + ", ".join(candidate.benchmark_skill_tags),
    ]
    return "\n".join(part for part in parts if part.strip())


def _skill_id(candidate: CandidateSkill) -> str:
    semantic_value = {
        "domain": candidate.domain,
        "skill_type": candidate.skill_type,
        "title": candidate.title.strip().lower(),
        "description": candidate.description.strip().lower(),
        "when_to_use": candidate.when_to_use,
        "procedure": [
            {
                "instruction": step.instruction,
                "action_template": step.action_template,
                "expected_observation": step.expected_observation,
            }
            for step in candidate.procedure
        ],
        "verification": candidate.verification,
    }
    encoded = json.dumps(
        semantic_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    suffix = hashlib.sha256(encoded).hexdigest()[:16]
    prefix = "cross" if candidate.domain == "cross_domain" else candidate.domain
    return f"skill_{prefix}_{suffix}"


def _validate_compact_candidate(envelope, traces):
    try:
        candidate = CompactSkill.model_validate(envelope.candidate)
        if envelope.finish_reason in {"length", "max_tokens"}:
            raise ValueError("generation_truncated")
        if _contains_truncated_text(envelope.candidate):
            raise ValueError("candidate_contains_truncated_text")
        if len(envelope.trace_ids) != 1:
            raise ValueError("compact_skill_requires_one_source_trajectory")
        trace = traces[envelope.trace_ids[0]]
        if trace.domain != envelope.domain or trace.task_id != envelope.task_id:
            raise ValueError("source_task_mismatch")
        if trace.error or trace.evaluation_outcome not in {"correct", "incorrect"}:
            raise ValueError("invalid_source_outcome")
    except (ValueError, KeyError) as exc:
        return None, {"generation_id": envelope.generation_id,
                      "stage": "quality_validation", "reasons": [str(exc)]}
    content = candidate.model_dump()
    digest = hashlib.sha256(json.dumps([trace.domain, content], sort_keys=True).encode()).hexdigest()[:16]
    record = CompactSkillRecord(
        **content, skill_id=f"skill_{trace.domain}_{digest}", domain=trace.domain,
        source_trace_ids=[trace.trace_id], benchmark_skill_tags=trace.benchmark_skill_tags,
        retrieval_text="\n".join(content.values()),
        evidence=SkillEvidence(successful_trace_ids=[trace.trace_id] if trace.succeeded else [],
            failed_trace_ids=[] if trace.succeeded else [trace.trace_id],
            success_count=int(trace.succeeded), failure_count=int(not trace.succeeded),
            source_task_ids=[trace.task_id]),
        quality=QualityAssessment(valid=True, score=1.0),
        provenance=SkillProvenance(generator_backend=envelope.generator_backend,
            generator_model=envelope.generator_model, prompt_version=envelope.prompt_version,
            generated_at=envelope.generated_at, raw_generation_id=envelope.generation_id,
            merged_raw_generation_ids=[envelope.generation_id]),
    )
    return record, None


def _validate_candidate(
    envelope: RawCandidateEnvelope,
    traces: dict[str, TrajectoryRecord],
) -> tuple[SkillRecord | None, dict[str, Any] | None]:
    if "principle" in envelope.candidate or envelope.prompt_version.startswith("gobrowse-compact"):
        return _validate_compact_candidate(envelope, traces)
    raw = envelope.candidate
    missing_fields = sorted(REQUIRED_CANDIDATE_FIELDS.difference(raw))
    issues: list[str] = []
    truncated = envelope.finish_reason in {"length", "max_tokens"}
    if truncated:
        issues.append("generation_truncated")
    if _contains_truncated_text(raw):
        issues.append("candidate_contains_truncated_text")
        truncated = True

    try:
        candidate = CandidateSkill.model_validate(raw)
    except ValidationError as exc:
        missing_fields = sorted(
            set(missing_fields).union(_missing_fields_from_validation(exc))
        )
        return None, {
            "generation_id": envelope.generation_id,
            "candidate_index": envelope.candidate_index,
            "stage": "quality_validation",
            "reasons": issues + ["schema_validation_failed"],
            "missing_fields": missing_fields,
            "validation_errors": exc.errors(include_url=False),
        }

    if candidate.domain != envelope.domain:
        issues.append("candidate_domain_does_not_match_source_domain")
    allowed_trace_ids = set(envelope.trace_ids)
    unknown_trace_ids = sorted(set(candidate.source_trace_ids).difference(allowed_trace_ids))
    if unknown_trace_ids:
        issues.append("unknown_source_trace_ids")
    known_source_ids = [
        trace_id
        for trace_id in candidate.source_trace_ids
        if trace_id in allowed_trace_ids and trace_id in traces
    ]
    if len(known_source_ids) < 2:
        issues.append("insufficient_multi_rollout_evidence")

    source_traces = [traces[trace_id] for trace_id in known_source_ids]
    allowed_tags = {
        tag for trace in source_traces for tag in trace.benchmark_skill_tags
    }
    unsupported_tags = sorted(set(candidate.benchmark_skill_tags).difference(allowed_tags))
    if unsupported_tags:
        issues.append("unsupported_benchmark_tags_removed")
        candidate.benchmark_skill_tags = [
            tag for tag in candidate.benchmark_skill_tags if tag in allowed_tags
        ]
    if any(not trace.succeeded for trace in source_traces) and not candidate.failure_modes:
        issues.append("failure_evidence_without_failure_mode")
    if not any(trace.succeeded for trace in source_traces) and candidate.skill_type != "recovery":
        issues.append("non_recovery_skill_has_no_success_evidence")

    hard_failures = {
        "generation_truncated",
        "candidate_contains_truncated_text",
        "candidate_domain_does_not_match_source_domain",
        "unknown_source_trace_ids",
        "non_recovery_skill_has_no_success_evidence",
    }
    valid = not hard_failures.intersection(issues) and bool(known_source_ids)
    score = 1.0
    score -= 0.12 * len([issue for issue in issues if issue not in hard_failures])
    score -= 0.35 * len(hard_failures.intersection(issues))
    score = max(0.0, min(1.0, score))
    quality = QualityAssessment(
        valid=valid,
        truncated=truncated,
        missing_fields=missing_fields,
        issues=issues,
        score=score,
    )
    if not valid:
        return None, {
            "generation_id": envelope.generation_id,
            "candidate_index": envelope.candidate_index,
            "stage": "quality_validation",
            "reasons": issues or ["quality_validation_failed"],
            "missing_fields": missing_fields,
        }

    candidate.source_trace_ids = list(dict.fromkeys(known_source_ids))
    successful = [trace.trace_id for trace in source_traces if trace.succeeded]
    failed = [trace.trace_id for trace in source_traces if not trace.succeeded]
    evidence = SkillEvidence(
        successful_trace_ids=successful,
        failed_trace_ids=failed,
        success_count=len(successful),
        failure_count=len(failed),
        source_task_ids=sorted({trace.task_id for trace in source_traces}),
    )
    provenance = SkillProvenance(
        generator_backend=envelope.generator_backend,
        generator_model=envelope.generator_model,
        prompt_version=envelope.prompt_version,
        generated_at=envelope.generated_at,
        raw_generation_id=envelope.generation_id,
        merged_raw_generation_ids=[envelope.generation_id],
    )
    return (
        SkillRecord(
            **candidate.model_dump(mode="python"),
            skill_id=_skill_id(candidate),
            retrieval_text=_retrieval_text(candidate),
            evidence=evidence,
            quality=quality,
            provenance=provenance,
        ),
        None,
    )


def postprocess_skill_bank(
    settings: Settings,
    *,
    embedder: Embedder | None = None,
) -> dict[str, int]:
    """Run the required quality -> embedding -> clustering/dedup sequence."""

    traces = _load_traces(settings)
    artifacts = settings.paths.artifacts_dir
    generation_path = artifacts / "raw_generations.jsonl"
    candidate_path = artifacts / "raw_candidates.jsonl"

    try:
        raw_generations = list(iter_jsonl(generation_path))
    except FileNotFoundError:
        raw_generations = []
    try:
        raw_candidates = list(iter_jsonl(candidate_path))
    except FileNotFoundError:
        raw_candidates = []

    accepted_generation_ids = {row.get("generation_id") for row in raw_candidates}
    rejected: list[dict[str, Any]] = []
    for generation in raw_generations:
        if generation.get("generation_id") in accepted_generation_ids:
            continue
        reasons = []
        if generation.get("parse_error"):
            reasons.append("generation_json_parse_failed")
        if generation.get("finish_reason") in {"length", "max_tokens"}:
            reasons.append("generation_truncated")
        if reasons:
            rejected.append(
                {
                    "generation_id": generation.get("generation_id"),
                    "stage": "generation_quality",
                    "reasons": reasons,
                    "parse_error": generation.get("parse_error"),
                }
            )

    validated: list[SkillRecord] = []
    for raw in raw_candidates:
        try:
            envelope = RawCandidateEnvelope.model_validate(raw)
        except ValidationError as exc:
            rejected.append(
                {
                    "generation_id": raw.get("generation_id"),
                    "candidate_index": raw.get("candidate_index"),
                    "stage": "candidate_envelope_validation",
                    "reasons": ["invalid_candidate_envelope"],
                    "validation_errors": exc.errors(include_url=False),
                }
            )
            continue
        skill, rejection = _validate_candidate(envelope, traces)
        if rejection is not None:
            rejected.append(rejection)
        elif skill is not None:
            validated.append(skill)

    atomic_write_json(
        artifacts / "validated_candidates.json",
        [skill.model_dump(mode="json") for skill in validated],
    )
    atomic_write_json(artifacts / "rejected_candidates.json", rejected)

    # Only the optional legacy strict mode withholds otherwise valid single sides.
    all_validated = list(validated)
    if settings.skill_build.selection == "outcome_pair" and settings.skill_build.require_outcome_pair:
        outcomes_by_task = {}
        for skill in validated:
            if isinstance(skill, CompactSkillRecord):
                trace = traces[skill.source_trace_ids[0]]
                outcomes_by_task.setdefault((trace.domain, trace.task_id), set()).add(trace.succeeded)
        validated = [skill for skill in validated if not isinstance(skill, CompactSkillRecord)
                     or outcomes_by_task[(skill.domain, traces[skill.source_trace_ids[0]].task_id)] == {True, False}]
    withheld_unpaired = len(all_validated) - len(validated)
    active_embedder = embedder or (create_embedder(settings) if validated else None)
    embedding_backend = active_embedder.name if active_embedder else settings.embedding.backend
    embedding_model = active_embedder.model_name if active_embedder else settings.embedding.model
    try:
        embeddings = (active_embedder.embed([skill.retrieval_text for skill in validated])
                      if active_embedder else np.empty((0, 0), dtype=np.float32))
    finally:
        if embedder is None and active_embedder is not None:
            active_embedder.close()
    if embeddings.ndim != 2 or embeddings.shape[0] != len(validated):
        raise ValueError(
            f"Embedding output shape {embeddings.shape} is incompatible with {len(validated)} skills"
        )
    atomic_save_numpy(artifacts / "skill_embeddings.npy", embeddings)
    dimensions = int(embeddings.shape[1]) if embeddings.shape[1:] else 0
    for index, skill in enumerate(validated):
        if dimensions > 0:
            skill.embedding = EmbeddingReference(
                backend=embedding_backend,
                model=embedding_model,
                dimensions=dimensions,
                vector_index=index,
            )

    pair_records = {}
    selection_path = artifacts / "selection_report.json"
    if selection_path.exists():
        for task in json.loads(selection_path.read_text())["tasks"]:
            key = f"{task['domain']}:{task['task_id']}"
            pair_records[key] = {"domain": task["domain"], "task_id": task["task_id"],
                                 "missing_outcomes": task["missing_outcomes"],
                                 "selected_trace_ids": task["selected_trace_ids"],
                                 "same_outcome_fallback": task.get("same_outcome_fallback", False),
                                 "positive": [], "negative": []}
    for skill in all_validated:
        for trace_id in skill.source_trace_ids:
            trace = traces[trace_id]
            key = f"{trace.domain}:{trace.task_id}"
            pair = pair_records.setdefault(key, {"domain": trace.domain, "task_id": trace.task_id,
                                                "positive": [], "negative": []})
            side = "positive" if trace.succeeded else "negative"
            pair[side].append({"trace_id": trace_id, "skill_id": skill.skill_id,
                              "skill": skill.model_dump(mode="json")})

    canonical, clusters, duplicates = cluster_and_deduplicate(
        validated,
        embeddings,
        threshold=settings.clustering.cosine_similarity_threshold,
        compare_within_domain=settings.clustering.compare_within_domain,
    )
    canonical_ids = {item["skill_id"]: item["duplicate_of"] for item in duplicates}
    published_ids = {skill.skill_id for skill in canonical}
    for pair in pair_records.values():
        pair["complete"] = bool(pair["positive"] and pair["negative"])
        pair["outcome_balanced"] = pair["complete"]
        available = {entry["trace_id"] for entry in pair["positive"] + pair["negative"]}
        selected = set(pair.get("selected_trace_ids", available))
        pair["extraction_complete"] = bool(selected) and selected.issubset(available)
        pair.setdefault("same_outcome_fallback", bool(selected) and
                        len({traces[trace_id].succeeded for trace_id in selected}) == 1)
        for entry in pair["positive"] + pair["negative"]:
            canonical_id = canonical_ids.get(entry["skill_id"], entry["skill_id"])
            entry["canonical_skill_id"] = canonical_id if canonical_id in published_ids else None
    atomic_write_json(artifacts / "skill_pairs.json", list(pair_records.values()))
    compact_bank = [{"skill_id": skill.skill_id, "title": skill.title,
                     "principle": skill.principle, "when_to_apply": skill.when_to_apply}
                    for skill in canonical if isinstance(skill, CompactSkillRecord)]
    atomic_write_json(artifacts / "skill_bank_compact.json", compact_bank)
    atomic_write_json(artifacts / "clusters.json", clusters)
    atomic_write_json(artifacts / "duplicates.json", duplicates)

    timestamp = _utc_now()
    metadata = SkillBankMetadata(
        bank_id="gobrowse_" + timestamp.replace(":", "").replace("-", ""),
        created_at=timestamp,
        schema_version="2.0" if settings.skill_build.schema_format == "compact" else "1.0",
        domains=settings.collection.domains,
        source_trajectory_count=len(traces),
        validated_candidate_count=len(validated),
        rejected_candidate_count=len(rejected),
        canonical_skill_count=len(canonical),
        duplicate_skill_count=len(duplicates),
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        clustering_threshold=settings.clustering.cosine_similarity_threshold,
    )
    skill_bank = SkillBank(metadata=metadata, skills=canonical)
    atomic_write_json(
        artifacts / "skill_bank.json", skill_bank.model_dump(mode="json")
    )

    issue_counts = Counter(
        reason
        for rejection in rejected
        for reason in rejection.get("reasons", [])
    )
    quality_report = {
        "pipeline_order": ["quality", "embedding", "clustering_deduplication"],
        "withheld_unpaired_candidates": withheld_unpaired,
        "complete_skill_pairs": sum(pair["complete"] for pair in pair_records.values()),
        "incomplete_skill_pairs": sum(not pair["complete"] for pair in pair_records.values()),
        "api_usage": {
            "reported_cost_usd": sum(g.get("cost") or 0 for g in raw_generations),
            "attempts_without_reported_cost": sum(g.get("cost") is None for g in raw_generations),
            "prompt_tokens": sum(g.get("prompt_tokens") or 0 for g in raw_generations),
            "completion_tokens_including_reasoning": sum(g.get("completion_tokens") or 0 for g in raw_generations),
            "reasoning_tokens": sum(g.get("reasoning_tokens") or 0 for g in raw_generations),
        },
        "source_trajectories": len(traces),
        "raw_generations": len(raw_generations),
        "raw_candidates": len(raw_candidates),
        "validated_candidates": len(validated),
        "rejected_records": len(rejected),
        "canonical_skills": len(canonical),
        "duplicates_removed": len(duplicates),
        "rejection_reason_counts": dict(sorted(issue_counts.items())),
        "embedding_shape": list(embeddings.shape),
        "clustering_threshold": settings.clustering.cosine_similarity_threshold,
    }
    atomic_write_json(artifacts / "quality_report.json", quality_report)
    return {
        "validated": len(validated),
        "rejected": len(rejected),
        "canonical": len(canonical),
        "duplicates": len(duplicates),
    }
