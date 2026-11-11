from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from .schemas import ClusterInfo, SkillRecord


def _canonical_score(skill: SkillRecord) -> tuple[float, int, int, str]:
    evidence_count = skill.evidence.success_count + skill.evidence.failure_count
    structural_detail = (
        len(getattr(skill, "procedure", [])) + len(getattr(skill, "verification", [])) + len(getattr(skill, "failure_modes", []))
    )
    return (
        skill.quality.score,
        evidence_count,
        structural_detail,
        skill.skill_id,
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _merge_evidence(canonical: SkillRecord, duplicates: list[SkillRecord]) -> None:
    for duplicate in duplicates:
        canonical.provenance.merged_raw_generation_ids = _unique(
            canonical.provenance.merged_raw_generation_ids
            + duplicate.provenance.merged_raw_generation_ids
            + [duplicate.provenance.raw_generation_id]
        )
        canonical.source_trace_ids = _unique(
            canonical.source_trace_ids + duplicate.source_trace_ids
        )
        canonical.benchmark_skill_tags = _unique(
            canonical.benchmark_skill_tags + duplicate.benchmark_skill_tags
        )
        canonical.evidence.successful_trace_ids = _unique(
            canonical.evidence.successful_trace_ids
            + duplicate.evidence.successful_trace_ids
        )
        canonical.evidence.failed_trace_ids = _unique(
            canonical.evidence.failed_trace_ids + duplicate.evidence.failed_trace_ids
        )
        canonical.evidence.source_task_ids = _unique(
            canonical.evidence.source_task_ids + duplicate.evidence.source_task_ids
        )
    canonical.evidence.success_count = len(canonical.evidence.successful_trace_ids)
    canonical.evidence.failure_count = len(canonical.evidence.failed_trace_ids)


def _complete_linkage_groups(
    indices: list[int], normalized: np.ndarray, threshold: float
) -> list[list[int]]:
    if len(indices) <= 1:
        return [indices]
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as exc:
        # Keep tiny CPU smoke tests dependency-free. Production banks should use
        # scikit-learn's optimized implementation through the declared dependency.
        if len(indices) > 64:
            raise RuntimeError(
                "Complete-linkage deduplication for more than 64 skills needs "
                "scikit-learn>=1.4. Install with: pip install -e ."
            ) from exc
        clusters = [[index] for index in indices]
        while True:
            best: tuple[float, int, int] | None = None
            for left in range(len(clusters)):
                for right in range(left + 1, len(clusters)):
                    cross = normalized[clusters[left]] @ normalized[clusters[right]].T
                    complete_similarity = float(cross.min())
                    if complete_similarity < threshold:
                        continue
                    candidate = (complete_similarity, -left, -right)
                    if best is None or candidate > best:
                        best = candidate
            if best is None:
                break
            left = -best[1]
            right = -best[2]
            clusters[left] = sorted(clusters[left] + clusters[right])
            del clusters[right]
        return sorted(clusters, key=lambda members: min(members))
    clusterer = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1.0 - threshold,
        metric="cosine",
        linkage="complete",
        compute_full_tree=True,
    )
    labels = clusterer.fit_predict(normalized[indices])
    grouped: dict[int, list[int]] = defaultdict(list)
    for index, label in zip(indices, labels):
        grouped[int(label)].append(index)
    return sorted(grouped.values(), key=lambda members: min(members))


def _select_medoid(members: list[int], normalized: np.ndarray, skills: list[SkillRecord]) -> int:
    if len(members) == 1:
        return members[0]
    member_embeddings = normalized[members]
    similarities = member_embeddings @ member_embeddings.T
    mean_similarities = (similarities.sum(axis=1) - 1.0) / (len(members) - 1)
    best_mean = float(mean_similarities.max())
    tied = [
        members[position]
        for position, value in enumerate(mean_similarities)
        if np.isclose(float(value), best_mean, rtol=1e-7, atol=1e-8)
    ]
    return max(tied, key=lambda index: _canonical_score(skills[index]))


def cluster_and_deduplicate(
    skills: list[SkillRecord],
    embeddings: np.ndarray,
    *,
    threshold: float,
    compare_within_domain: bool,
) -> tuple[list[SkillRecord], list[dict[str, Any]], list[dict[str, Any]]]:
    """Complete-link cosine clustering followed by medoid deduplication."""

    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be a rank-2 matrix")
    if embeddings.shape[0] != len(skills):
        raise ValueError(
            f"Embedding row count {embeddings.shape[0]} does not match skill count {len(skills)}"
        )
    if not skills:
        return [], [], []

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.maximum(norms, 1e-12)
    partitions: dict[str, list[int]] = defaultdict(list)
    for index, skill in enumerate(skills):
        key = skill.domain if compare_within_domain else "all"
        partitions[key].append(index)
    groups: list[list[int]] = []
    for key in sorted(partitions):
        groups.extend(
            _complete_linkage_groups(partitions[key], normalized, threshold)
        )

    canonical_skills: list[SkillRecord] = []
    cluster_manifest: list[dict[str, Any]] = []
    duplicate_manifest: list[dict[str, Any]] = []
    ordered_groups = sorted(groups, key=lambda members: min(members))
    for ordinal, members in enumerate(ordered_groups, start=1):
        cluster_id = f"cluster_{ordinal:06d}"
        canonical_index = _select_medoid(members, normalized, skills)
        canonical = skills[canonical_index]
        duplicates = [skills[index] for index in members if index != canonical_index]
        _merge_evidence(canonical, duplicates)
        canonical.cluster = ClusterInfo(cluster_id=cluster_id, canonical=True)
        canonical_skills.append(canonical)

        member_records: list[dict[str, Any]] = []
        for index in members:
            similarity = float(np.dot(normalized[index], normalized[canonical_index]))
            similarity = max(-1.0, min(1.0, similarity))
            skill = skills[index]
            if index != canonical_index:
                skill.cluster = ClusterInfo(
                    cluster_id=cluster_id,
                    canonical=False,
                    duplicate_of=canonical.skill_id,
                    similarity_to_canonical=similarity,
                )
                duplicate_manifest.append(
                    {
                        "skill_id": skill.skill_id,
                        "duplicate_of": canonical.skill_id,
                        "cluster_id": cluster_id,
                        "similarity_to_canonical": similarity,
                    }
                )
            member_records.append(
                {
                    "skill_id": skill.skill_id,
                    "canonical": index == canonical_index,
                    "similarity_to_canonical": similarity,
                }
            )
        cluster_manifest.append(
            {
                "cluster_id": cluster_id,
                "domain": canonical.domain,
                "metric": "cosine",
                "linkage": "complete",
                "canonical_selection": "semantic_medoid",
                "canonical_skill_id": canonical.skill_id,
                "members": member_records,
            }
        )

    canonical_skills.sort(key=lambda skill: (skill.domain, skill.title, skill.skill_id))
    return canonical_skills, cluster_manifest, duplicate_manifest
