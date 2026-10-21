#!/usr/bin/env python3
"""Tiny local-model task runner; independent workdirs, no paid API by default.

Evaluator stays outside the agent cwd but is NOT protected from same-user shell
access. Use trusted demo tasks only. Each task gets one attempt.
"""
import argparse
import asyncio
import concurrent.futures
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python"))
from demo_tasks import TASKS, create_fixture, evaluate


def local_endpoint(url):
    parsed = urlparse(url)
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except (ValueError, TypeError):
        loopback = False
    if parsed.scheme not in {"http", "https"} or not loopback or parsed.username or parsed.password:
        raise ValueError("Demo permits only loopback model endpoints (use an SSH tunnel for a remote local model)")
    return url


def hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def run_one(task, output, model, api_base):
    task_dir = output / task["id"]
    task_dir.mkdir(parents=True, exist_ok=False)
    workdir = task_dir / "workspace"
    create_fixture(task["id"], workdir)
    before = hashes(workdir)
    env = dict(os.environ, MINI_CLAUDE_STATE_DIR=str(task_dir / "state"),
               MINI_CLAUDE_LOCAL_MODEL="1", MINI_CLAUDE_CONTEXT_WINDOW=os.getenv("MINI_CLAUDE_CONTEXT_WINDOW", "16384"),
               MINI_CLAUDE_MAX_OUTPUT_TOKENS=os.getenv("MINI_CLAUDE_MAX_OUTPUT_TOKENS", "2048"))
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--task", task["id"],
               "--output", str(task_dir), "--model", model, "--api-base", api_base]
    started = time.monotonic()
    with (task_dir / "run.log").open("w") as log:
        process = subprocess.Popen(command, cwd=workdir, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            status = "finished" if process.wait(timeout=600) == 0 else "runner_error"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            status = "timeout"
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    metadata = json.loads((task_dir / "model.json").read_text()) if (task_dir / "model.json").exists() else {}
    if status == "finished" and metadata.get("stop_reason") in {"turn_limit", "cost_limit"}:
        status = "budget_exhausted"
    if metadata.get("aborted"):
        status = "aborted" if status != "timeout" else status
    after = hashes(workdir)
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    artifacts_ok = set(changed) <= {"orders.py", "cli.py"}
    evaluation = evaluate(task["id"], workdir)
    evaluation["checks"].append({"name": "allowed_artifacts", "passed": artifacts_ok, "changed": changed})
    evaluation["passed"] = evaluation["passed"] and artifacts_ok
    result = {"task": task["id"], "split": task["split"], "status": status,
              "elapsed_seconds": round(time.monotonic() - started, 3), **metadata,
              "before_hashes": before, "after_hashes": after, "evaluation": evaluation}
    (task_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


async def worker(args, task):
    from mini_claude.agent import Agent
    from mini_claude.tools import tool_definitions
    names = {"read_file", "write_file", "edit_file", "list_files", "grep_search", "run_shell"}
    agent = Agent(model=args.model, api_base=args.api_base, api_key=os.getenv("OPENAI_API_KEY", "local"),
                  permission_mode="bypassPermissions", max_turns=10,
                  custom_tools=[t for t in tool_definitions if t["name"] in names])
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, agent.abort)
    try:
        result = await asyncio.wait_for(agent.run_once(task["prompt"] + "\nWork only in the current workspace. Only orders.py and cli.py may be changed; do not create other files. Do not inspect parent directories or evaluation code. Use sample.csv to test. Finish after implementing and testing the change."), timeout=570)
        metadata = {"session_id": agent.session_id, "tokens": result["tokens"], "response": result["text"], "aborted": agent._aborted, "stop_reason": result["stop_reason"]}
        (args.output / "model.json").write_text(json.dumps(metadata, indent=2))
        return 130 if agent._aborted else 0
    finally:
        try:
            (args.output / "transcript.json").write_text(json.dumps(agent._openai_messages, indent=2, default=str))
        finally:
            await agent.close()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list", action="store_true")
    p.add_argument("--verify-fixtures", action="store_true")
    p.add_argument("--task", choices=[t["id"] for t in TASKS])
    p.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    p.add_argument("--output", type=lambda s: Path(s).resolve(), default=Path.cwd() / "demo-results")
    p.add_argument("--workers", type=int, choices=[1, 2, 3], default=1)
    p.add_argument("--model", default=os.getenv("MINI_CLAUDE_MODEL", "qwen3-8b-local"))
    p.add_argument("--api-base", default=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8020/v1"))
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    selected = [t for t in TASKS if (t["id"] == args.task if args.task else args.split == "all" or t["split"] == args.split)]
    if args.list:
        print(json.dumps(TASKS, indent=2))
    elif args.verify_fixtures:
        with tempfile.TemporaryDirectory() as tmp:
            for task in TASKS:
                results = []
                for solved in (False, True):
                    directory = Path(tmp) / f"{task['id']}-{solved}"
                    create_fixture(task["id"], directory, solved)
                    results.append(evaluate(task["id"], directory)["passed"])
                print(task["id"], {"original_passes": results[0], "reference_passes": results[1]})
                if results != [False, True]:
                    raise SystemExit("Fixture failed verification")
    elif args.worker:
        local_endpoint(args.api_base)
        raise SystemExit(asyncio.run(worker(args, selected[0])))
    else:
        local_endpoint(args.api_base)
        args.output.mkdir(parents=True, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_one, t, args.output, args.model, args.api_base) for t in selected]
            results = [f.result() for f in futures]
        (args.output / "summary.json").write_text(json.dumps(results, indent=2))
        print(json.dumps([{"task": r["task"], "status": r["status"], "passed": r["evaluation"]["passed"]} for r in results]))


if __name__ == "__main__":
    main()
