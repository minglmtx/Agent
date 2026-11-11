"""Audit imported or online browser trajectories without assuming a fixed rollout count."""

from collections import Counter, defaultdict
from pathlib import Path
from .io_utils import iter_jsonl, atomic_write_json
from .schemas import TrajectoryRecord


def audit_trajectories(inputs, *, output_path=None):
    paths = []
    for item in inputs:
        p = Path(item)
        paths.extend(sorted(p.glob("*.jsonl")) if p.is_dir() else [p])
    ids = set()
    groups = defaultdict(list)
    invalid = []
    duplicates = []
    outcomes = Counter()
    for path in dict.fromkeys(paths):
        for raw in iter_jsonl(path):
            try:
                t = TrajectoryRecord.model_validate(raw)
            except ValueError:
                invalid.append({"path": str(path), "trace_id": raw.get("trace_id")})
                continue
            if t.trace_id in ids:
                duplicates.append(t.trace_id)
                continue
            ids.add(t.trace_id)
            groups[t.domain, t.task_id].append(t)
            outcomes[t.evaluation_outcome] += 1
    report = {
        "trajectories": len(ids),
        "task_groups": len(groups),
        "outcomes": dict(outcomes),
        "paired_tasks": sum(
            {"correct", "incorrect"}
            <= {t.evaluation_outcome for t in ts if not t.error and not t.quality_flags}
            for ts in groups.values()
        ),
        "singleton_tasks": sum(len(ts) == 1 for ts in groups.values()),
        "invalid_records": invalid,
        "duplicate_trace_ids": duplicates,
        "data_integrity_check_passed": not invalid and not duplicates,
        "quality_flagged": sum(
            bool(t.quality_flags) for ts in groups.values() for t in ts
        ),
        "runtime_errors": sum(
            t.error is not None for ts in groups.values() for t in ts
        ),
    }
    if output_path:
        atomic_write_json(output_path, report)
    return report
