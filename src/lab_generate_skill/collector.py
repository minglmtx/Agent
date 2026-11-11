"""Collect one independently configured live browser attempt per task manifest entry."""

import hashlib
import json
from pathlib import Path
from .gobrowse_runtime import load_browser_tasks, run_browser_rollout
from .io_utils import append_jsonl, iter_jsonl


def collect_trajectories(
    settings, backend, *, tasks_path, output_path=None, limit=None, rollout_index=0
):
    if rollout_index < 0 or (limit is not None and limit < 1):
        raise ValueError("Invalid rollout index or task limit")
    tasks = load_browser_tasks(tasks_path)
    tasks = [t for t in tasks if t.domain in settings.collection.domains]
    if limit is not None:
        tasks = tasks[:limit]
    output = (
        Path(output_path)
        if output_path
        else settings.paths.runtime_output_dir / "online_trajectories.jsonl"
    )
    protected = [Path(tasks_path).resolve()] + [
        (settings.paths.trajectories_dir / f"{d}.jsonl").resolve()
        for d in settings.collection.domains
    ]
    if output.resolve() in protected:
        raise ValueError("Runtime output must be separate from source data")
    if output.exists() and not settings.collection.resume:
        raise FileExistsError("Choose a new output path when resume is disabled")
    completed = (
        {r["trace_id"]: r for r in iter_jsonl(output)}
        if settings.collection.resume and output.exists()
        else {}
    )
    written = errors = unknown = 0
    for task in tasks:
        spec = {
            "task": task.model_dump(),
            "actor": settings.actor.model_dump(),
            "browser": settings.browser.model_dump(),
            "base_seed": settings.collection.base_seed,
        }
        fingerprint = hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest()
        trace_id = f"browser:{task.task_id}:rollout:{rollout_index}"
        if trace_id in completed:
            if (
                completed[trace_id].get("provenance", {}).get("runtime_spec_hash")
                != fingerprint
            ):
                raise ValueError("Runtime settings changed; use a new output file")
            if completed[trace_id].get("error"):
                errors += 1
            continue
        trace = run_browser_rollout(
            settings, backend, task, rollout_index=rollout_index
        )
        trace.provenance["runtime_spec_hash"] = fingerprint
        append_jsonl(output, [trace.model_dump(mode="json")])
        written += 1
        errors += trace.error is not None
        unknown += trace.evaluation_outcome == "unknown"
    return {
        "written": written,
        "runtime_errors": errors,
        "unlabeled": unknown,
        "output": str(output),
    }
