"""Stream Go-Browse-WA Parquet, select at most two attempts per goal, retain provenance."""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

import pyarrow.parquet as pq

from .config import Settings
from .io_utils import atomic_write_json
from .schemas import TraceMessage, TrajectoryRecord
from .skill_builder import _reservoir


def normalize_goal(goal: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", goal)).strip()


def task_group_id(domain: str, goal: str) -> str:
    return hashlib.sha256(
        json.dumps((domain, normalize_goal(goal)), ensure_ascii=False).encode()
    ).hexdigest()[:20]


def select_balanced(records: list[dict], seed: int) -> list[dict]:
    """Generative-skill Algorithm R: one of each outcome, same-class fallback, max two."""
    rng = random.Random(seed)
    ordered = sorted(records, key=lambda r: int(r["source_id"]))
    pos = _reservoir((r for r in ordered if r["success"]), 2, rng)
    neg = _reservoir((r for r in ordered if not r["success"]), 2, rng)
    selected = pos[:1] + neg[:1]
    selected += (pos[1:] + neg[1:])[: 2 - len(selected)]
    return selected


def _rows(files, columns):
    for path in files:
        print(f"Reading {path.name}", flush=True)
        row_number = 0
        for batch in pq.ParquetFile(path).iter_batches(
            batch_size=128, columns=columns, use_threads=False
        ):
            for row in batch.to_pylist():
                yield path, row_number, row["json"]
                row_number += 1


def convert_trajectory(
    meta: dict, steps: list[dict], rollout_index: int, seed: int, revision: str
):
    steps = sorted(steps, key=lambda r: r["step_number"])
    flags = []
    if [r["step_number"] for r in steps] != list(range(meta["expected_steps"])):
        flags.append("missing_or_duplicate_steps")
    if bool(meta["success"]) != (meta["reward"] > 0):
        flags.append("reward_success_disagree")
    messages = []
    for step in steps:
        obs = step["obs"]
        if not (obs.get("axtree_txt") or "").strip():
            flags.append("missing_observation")
        action = step.get("parsed_action") or ""
        raw = step.get("action") or ""
        if not action.strip() and not raw.strip():
            flags.append("missing_action")
        # Browser errors and unparseable model actions are legitimate failure evidence.
        content = json.dumps(
            {
                "axtree": obs.get("axtree_txt"),
                "last_action": obs.get("last_action"),
                "last_action_error": obs.get("last_action_error"),
            },
            ensure_ascii=False,
        )
        messages.append(TraceMessage(turn=len(messages), role="user", content=content))
        completion = json.dumps(
            {"thought": step.get("thought"), "action": action, "raw_response": raw},
            ensure_ascii=False,
        )
        messages.append(
            TraceMessage(
                turn=len(messages),
                role="assistant",
                content=completion,
                action_kind="browsergym",
                action_payload=action or None,
            )
        )
    if (
        meta["success"]
        and steps
        and "report_infeasible(" in (steps[-1].get("parsed_action") or "")
    ):
        flags.append("successful_infeasible_action")
    if not steps:
        flags.append("empty_trajectory")
    record = TrajectoryRecord(
        trace_id=f"gobrowse:{meta['source_id']}",
        domain=meta["domain"],
        task_id=meta["task_group_id"],
        rollout_index=rollout_index,
        seed=seed,
        task_instruction=meta["goal"],
        model=",".join(sorted(meta["models"])),
        system_prompt="",
        messages=messages,
        sample_status="imported",
        evaluation_outcome="correct" if meta["success"] else "incorrect",
        finish_reason="source_trajectory_end",
        rounds=len(steps),
        started_at="",
        finished_at="",
        task_output={"response": meta.get("response"), "reward": meta["reward"]},
        quality_flags=sorted(set(flags)),
        provenance={
            "dataset": "apurvaga/go-browse-wa-raw",
            "revision": revision,
            "source_trajectory_id": meta["source_id"],
            "outcome_source": "source_vlm_judge",
            "source_node_url": meta["source_node_url"],
            "root_url": meta["root_url"],
            "actual_start_url": None,
            "start_state_verified": False,
            "actor_seed": None,
            "seed_semantics": "preparation/extraction seed, not original actor seed",
            "grouping": "website + normalized exact goal; source page ignored",
            "source_rows": [
                {"parquet": s["_file"], "row": s["_row"], "step": s["step_number"]}
                for s in steps
            ],
            "observation_format": "axtree_txt; screenshots remain in raw Parquet",
            "terminal_observation_available": False,
        },
    )
    return record


def preprocess_gobrowse(settings: Settings, *, overwrite: bool = False) -> dict:
    raw = settings.paths.gobrowse_raw
    out = settings.paths.prepared_dir
    out.mkdir(parents=True, exist_ok=True)
    if (out / "preprocessing_report.json").exists() and not overwrite:
        raise FileExistsError(
            "Prepared data already exists; use --overwrite to regenerate it"
        )
    files = sorted((raw / "data").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Go-Browse Parquet in {raw}/data")
    manifest_path = raw.parent / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    revision = manifest.get("revision", "unrecorded")
    for f in manifest.get("files", []):
        p = raw / f["path"]
        if not p.is_file() or p.stat().st_size != f["size"]:
            raise ValueError(f"Incomplete source snapshot: {p}")
    metas = {}
    columns = [
        "json.graph_data",
        "json.node_data",
        "json.traj_data",
        "json.step_data.step_number",
        "json.step_data.misc.agent_config.model_id",
    ]
    for path, rownum, j in _rows(files, columns):
        t = j["traj_data"]
        domain = j["graph_data"]["domain"]
        if domain not in settings.collection.domains:
            continue
        key = str(t["traj_num"])
        basic = {
            "source_id": key,
            "domain": domain,
            "goal": t["goal"],
            "task_group_id": task_group_id(domain, t["goal"]),
            "success": t["success"],
            "reward": t["reward"],
            "expected_steps": t["traj_length"],
            "source_node_url": j["node_data"]["node_url"],
            "root_url": j["graph_data"]["root_url"],
            "response": t.get("response"),
        }
        if key not in metas:
            metas[key] = {**basic, "models": set(), "step_numbers": []}
        m = metas[key]
        if any(m[k] != v for k, v in basic.items()):
            raise ValueError(f"Inconsistent trajectory metadata: {key}")
        m["models"].add(j["step_data"]["misc"]["agent_config"]["model_id"] or "unknown")
        m["step_numbers"].append(j["step_data"]["step_number"])
    groups = collections.defaultdict(list)
    for m in metas.values():
        groups[m["task_group_id"]].append(m)
    selected = {}
    selection = []
    for key, records in sorted(groups.items()):
        seed = settings.collection.base_seed + int(key[:8], 16)
        chosen = select_balanced(records, seed)
        for index, m in enumerate(chosen):
            selected[m["source_id"]] = (m, index)
        pos = sum(r["success"] for r in records)
        selection.append(
            {
                "task_id": key,
                "domain": records[0]["domain"],
                "goal": normalize_goal(records[0]["goal"]),
                "available_positive": pos,
                "available_negative": len(records) - pos,
                "paired": bool(pos and pos < len(records)),
                "selected_trace_ids": [f"gobrowse:{r['source_id']}" for r in chosen],
                "source_node_urls": sorted({r["source_node_url"] for r in records}),
                "runtime_ready": False,
                "runtime_requirement": "Supply explicit current start URL and reset/evaluation configuration",
            }
        )
    # Disk staging keeps peak memory independent of the selected observation corpus size.
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=out) as td:
        stage = Path(td)
        con = sqlite3.connect(stage / "steps.sqlite")
        con.execute("CREATE TABLE steps (id TEXT, n INTEGER, payload TEXT)")
        columns = [
            "json.traj_data.traj_num",
            "json.step_data.action",
            "json.step_data.parsed_action",
            "json.step_data.thought",
            "json.step_data.step_number",
            "json.step_data.obs.axtree_txt",
            "json.step_data.obs.last_action",
            "json.step_data.obs.last_action_error",
        ]
        for path, rownum, j in _rows(files, columns):
            key = str(j["traj_data"]["traj_num"])
            if key in selected:
                step = j["step_data"]
                step["_file"] = str(path.relative_to(raw))
                step["_row"] = rownum
                con.execute(
                    "INSERT INTO steps VALUES (?,?,?)",
                    (key, step["step_number"], json.dumps(step)),
                )
        con.commit()
        con.execute("CREATE INDEX by_traj ON steps(id,n)")
        handles = {}
        accepted = collections.Counter()
        rejected = []
        candidate_counts = collections.Counter()
        try:
            for folder in ("candidates", "trajectories"):
                (stage / folder).mkdir()
                for domain in settings.collection.domains:
                    handles[folder, domain] = (stage / folder / f"{domain}.jsonl").open(
                        "w"
                    )
            for key, (meta, index) in sorted(
                selected.items(),
                key=lambda x: (x[1][0]["domain"], x[1][0]["task_group_id"], x[1][1]),
            ):
                steps = [
                    json.loads(r[0])
                    for r in con.execute(
                        "SELECT payload FROM steps WHERE id=? ORDER BY n", (key,)
                    )
                ]
                trace = convert_trajectory(
                    meta, steps, index, settings.collection.base_seed, revision
                )
                line = trace.model_dump_json() + "\n"
                domain = trace.domain
                handles["candidates", domain].write(line)
                candidate_counts[domain] += 1
                if trace.quality_flags:
                    rejected.append(
                        {
                            "trace_id": trace.trace_id,
                            "task_id": trace.task_id,
                            "flags": trace.quality_flags,
                        }
                    )
                else:
                    handles["trajectories", domain].write(line)
                    accepted[domain] += 1
        finally:
            for f in handles.values():
                f.close()
            con.close()
        for folder in ("candidates", "trajectories"):
            destination = (
                out / folder
                if folder == "candidates"
                else settings.paths.trajectories_dir
            )
            destination.mkdir(parents=True, exist_ok=True)
            for domain in settings.collection.domains:
                (stage / folder / f"{domain}.jsonl").replace(
                    destination / f"{domain}.jsonl"
                )
    report = {
        "source_revision": revision,
        "grouping": "website + normalized exact goal; ignore source page",
        "seed": settings.collection.base_seed,
        "source_trajectories": len(metas),
        "task_groups": len(groups),
        "paired_tasks": sum(r["paired"] for r in selection),
        "success_only_tasks": sum(r["available_negative"] == 0 for r in selection),
        "failure_only_tasks": sum(r["available_positive"] == 0 for r in selection),
        "candidate_trajectories": len(selected),
        "accepted_trajectories": sum(accepted.values()),
        "rejected_trajectories": len(rejected),
        "accepted_by_domain": dict(accepted),
        "candidate_by_domain": dict(candidate_counts),
        "policy": "max two; prefer one success and one failure; fallback same outcome; singleton retained",
        "selection_precedes_quality_filter": True,
        "api_calls": 0,
    }
    atomic_write_json(out / "selection_manifest.json", selection)
    atomic_write_json(out / "quality_rejections.json", rejected)
    atomic_write_json(out / "preprocessing_report.json", report)
    return report
