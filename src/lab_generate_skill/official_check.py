"""Readiness checks for actual WebArena tasks; no model or judge API calls."""

from __future__ import annotations
import importlib.metadata
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import requests
from .io_utils import atomic_write_json


def check_official(task_ids: list[int], config_file: Path, output: Path | None = None):
    configs = {r["task_id"]: r for r in json.loads(config_file.read_text())}
    selected = [configs[i] for i in task_ids]
    required = sorted({site for t in selected for site in t["sites"]})
    sites = {}
    problems = []
    for site in required:
        variable = "WA_" + site.upper()
        url = os.environ.get(variable, "")
        status = {"configured": bool(url and url != "todo"), "reachable": False}
        if not status["configured"]:
            problems.append(f"{variable} is not configured")
        elif urlparse(url).scheme not in {"http", "https"}:
            problems.append(f"{variable} must be an http(s) URL")
        else:
            try:
                r = requests.get(url, timeout=10)
                status["http_status"] = r.status_code
                status["reachable"] = r.status_code < 400
                if not status["reachable"]:
                    problems.append(f"{variable} HTTP {r.status_code}")
            except requests.RequestException as exc:
                status["error"] = type(exc).__name__
                problems.append(f"{variable} cannot be reached")
        sites[site] = status
    report = {
        "task_ids": task_ids,
        "tasks": [
            {
                "task_id": t["task_id"],
                "sites": t["sites"],
                "intent": t["intent"],
                "eval_types": t["eval"]["eval_types"],
            }
            for t in selected
        ],
        "sites": sites,
        "ready_for_browser_attempt": not problems,
        "problems": problems,
        "official_evaluation_executed": False,
        "note": "Reachability is a prerequisite, not proof of login, snapshot identity, or evaluation success.",
    }
    for name in ["browsergym-core", "browsergym-webarena", "libwebarena"]:
        try:
            report[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report[name] = None
            report["ready_for_browser_attempt"] = False
            problems.append(f"Missing {name}")
    if output:
        atomic_write_json(output, report)
    return report
