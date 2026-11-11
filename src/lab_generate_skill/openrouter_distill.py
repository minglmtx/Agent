"""CPU-only OpenRouter entrypoint reusing the existing candidate ledger/pipeline.

Model and request defaults follow generative_skill/extract_alfworld_skills.py.
Requests are sequential; completed responses are durable and recoverable.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path

import requests
import yaml

from .billing import cost_state, no_charge, reservation_estimate, reserve_unknown_requests, valid_cost
from .config import load_settings
from .io_utils import atomic_write_json, iter_jsonl
from .llm import create_chat_backend, exception_diagnostics
from .skill_builder import build_raw_candidates, prepare_skill_inputs

MODELS_URL = "https://openrouter.ai/api/v1/models"


def check_model(settings):
    """Public, non-generation request; never sends the user's API key."""
    try:
        response = requests.get(MODELS_URL, timeout=30)
        response.raise_for_status()
        models = response.json()["data"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise RuntimeError(f"Cannot read public OpenRouter catalog ({type(exc).__name__})") from None
    matches = [m for m in models if m["id"] == settings.skill_extractor.model]
    if not matches:
        raise RuntimeError("Configured model ID is absent from the OpenRouter catalog; set --model explicitly")
    model = matches[0]
    supported = set(model.get("supported_parameters") or [])
    if not {"response_format", "structured_outputs"} & supported:
        raise RuntimeError("Configured model does not advertise structured JSON output")
    caps = settings.skill_extractor.provider_max_price or {}
    base_prices = {}
    for key in ("prompt", "completion"):
        if model.get("pricing", {}).get(key) is not None:
            base_prices[key] = float(model["pricing"][key]) * 1_000_000
            if key in caps and base_prices[key] > caps[key] + 1e-9:
                raise RuntimeError(f"Catalog {key} price exceeds the configured provider price cap")
    return {
        "model": model["id"], "context_length": model.get("context_length"),
        "base_usd_per_million_tokens": base_prices,
        "provider_price_caps": caps, "pricing": model.get("pricing", {}),
        "supported_parameters": sorted(supported),
        "note": "Public catalog check only; account access and provider routing require a real request. Long-context prices may differ.",
    }


@contextmanager
def output_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".distill.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another distillation process owns this output directory") from None
        yield


def ensure_run_manifest(settings):
    """Do not reuse paid results across different prompts, models, or inputs."""
    files = [settings.paths.trajectories_dir / f"{d}.jsonl" for d in settings.collection.domains]
    inputs = [{"path": str(p.resolve()), "size": p.stat().st_size,
               "mtime_ns": p.stat().st_mtime_ns} for p in files]
    spec = {
        "prompt_sha256": hashlib.sha256(settings.paths.prompt_template.read_bytes()).hexdigest(),
        "skill_build": settings.skill_build.model_dump(mode="json"),
        "extractor": settings.skill_extractor.model_dump(mode="json"),
        "collection": settings.collection.model_dump(mode="json"),
        "inputs": inputs,
    }
    path = settings.paths.artifacts_dir / "distill_manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != spec:
            raise RuntimeError("Prompt/model/input settings changed; choose a new --output-dir")
    else:
        if any((settings.paths.artifacts_dir / name).exists() for name in
               ("raw_candidates.jsonl", "raw_generations.jsonl")):
            raise RuntimeError("Existing extraction ledgers have no matching manifest; choose a new --output-dir")
        atomic_write_json(path, spec)
    # All paths are resolved; only the environment variable NAME is stored, never the key.
    config_path = settings.paths.artifacts_dir / "run_config.yaml"
    config_path.write_text(yaml.safe_dump(settings.model_dump(mode="json"), sort_keys=False))


class BudgetStop(RuntimeError):
    pass


class ProgressBackend:
    def __init__(self, backend, *, directory=None, max_cost_usd=None, max_run_seconds=None, max_prompt_bytes=None,
                 max_unconfirmed_requests=0, unknown_estimate=None):
        self.backend = backend
        self.name, self.model_name = backend.name, backend.model_name
        self.calls = 0
        self.max_cost_usd = max_cost_usd
        self.deadline = time.monotonic() + max_run_seconds if max_run_seconds is not None else None
        self.max_prompt_bytes = max_prompt_bytes
        self.directory = directory
        self.max_unconfirmed_requests = max_unconfirmed_requests
        self.unknown_estimate = unknown_estimate
        self.quarantined = set()
        self.reconciled = 0.0
        self.reserved = 0.0
        self.spent = 0.0
        self.unknown_cost = False
        if directory is not None:
            self._sync_billing()

    def _sync_billing(self):
        state, self.quarantined, over_limit = reserve_unknown_requests(
            self.directory, limit=self.max_unconfirmed_requests, estimate=self.unknown_estimate)
        self.spent = state['reported_cost_usd']
        self.reconciled = state['reconciled_cost_usd']
        self.reserved = state['reserved_unconfirmed_cost_usd']
        self.unknown_cost = bool(state['unreserved_unknown_calls']) or over_limit

    def is_quarantined(self, generation_id):
        return generation_id in self.quarantined

    def after_record(self, record):
        # Only rescan the ledger for uncertain charges, not for every paid success.
        if not valid_cost(record.get('cost')) and not no_charge(record):
            self.quarantined.add(record['generation_id'])
            if self.directory is not None:
                self._sync_billing()

    def check_unknown_budget(self):
        if self.unknown_cost:
            raise BudgetStop("Missing API cost: unresolved request allowance exhausted or no reliable reservation; reconcile billing")

    def check_input(self, messages):
        size = sum(len(m['content'].encode('utf-8')) for m in messages)
        if self.max_prompt_bytes is not None and size > self.max_prompt_bytes:
            return dict(reason='oversized_input_quarantined', prompt_utf8_bytes=size,
                        limit_bytes=self.max_prompt_bytes)
        return None

    def before_request(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise BudgetStop("Run time stop line reached; resume with the same command")
        self.check_unknown_budget()
        if self.max_cost_usd is None:
            return
        accounted = self.spent + self.reconciled + self.reserved
        # With the bounded policy, leave room for the next request's full estimate.
        next_reserve = self.unknown_estimate['reserved_usd'] if self.unknown_estimate else 0.0
        if accounted >= self.max_cost_usd or accounted + next_reserve > self.max_cost_usd:
            raise BudgetStop(f"Reported plus reconciled/reserved API cost ${accounted:.6f} leaves insufficient room below stop line ${self.max_cost_usd:.2f}")

    def generate(self, messages, *, seed):
        self.calls += 1
        print(json.dumps({"event": "api_request", "request_in_this_run": self.calls,
                          "prompt_characters": sum(len(m["content"]) for m in messages)}), flush=True)
        try:
            result = self.backend.generate(messages, seed=seed)
        except Exception as exc:
            # A 429 is a rejected request. Timeouts/5xx may have been billed.
            result = getattr(exc, 'generation_result', None)
            if result is not None and isinstance(result.cost, (int, float)) and math.isfinite(result.cost) and result.cost >= 0:
                self.spent += result.cost
            elif getattr(exc, "status_code", None) != 429 and not exception_diagnostics(exc)['request_not_sent']:
                self.unknown_cost = True
            raise
        if result.cost is None or not math.isfinite(result.cost) or result.cost < 0:
            self.unknown_cost = True
        else:
            self.spent += result.cost
        print(json.dumps({"event": "api_response", "request_in_this_run": self.calls,
                          "finish_reason": result.finish_reason,
                          "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
                          "reported_cost_usd": result.cost}), flush=True)
        return result


def export_candidates(directory):
    """A compact, unmerged candidate list, separate from audit metadata."""
    records = []
    path = directory / "raw_candidates.jsonl"
    if path.exists():
        for row in iter_jsonl(path):
            records.append({"skill_id": "candidate_" + hashlib.sha256(row["generation_id"].encode()).hexdigest()[:20],
                            **row["candidate"]})
    temporary = directory / ".candidate_skills.jsonl.tmp"
    with temporary.open("w") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(directory / "candidate_skills.jsonl")
    totals = {"calls": 0, "failed_attempts": 0, "prompt_tokens": 0,
              "completion_tokens": 0, "reasoning_tokens": 0, "reported_cost_usd": 0.0,
              "calls_without_reported_cost": 0, "candidate_skills": len(records)}
    ledger = directory / "raw_generations.jsonl"
    if ledger.exists():
        for row in iter_jsonl(ledger):
            totals["calls"] += 1
            totals["failed_attempts"] += bool(row.get("parse_error"))
            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
                totals[key] += row.get(key) or 0
            if row.get("cost") is None:
                totals["calls_without_reported_cost"] += 1
            else:
                totals["reported_cost_usd"] += row["cost"]
    totals.update(cost_state(directory))
    atomic_write_json(directory / "usage_summary.json", totals)
    return totals


def parser():
    p = argparse.ArgumentParser(description="Distill Go-Browse skills with OpenRouter; no local GPU model")
    p.add_argument("--config", default=os.environ.get("LAB_SKILL_CONFIG", str(Path(__file__).parents[2] / "configs/default.yaml")))
    p.add_argument("--output-dir", type=Path, help="New/resumable directory; defaults to configured artifacts_dir")
    p.add_argument("--limit-tasks", type=int, help="Process the first N task groups, up to two trajectories each")
    p.add_argument("--max-prompt-bytes", type=int, default=500000,
                   help="Quarantine larger UTF-8 prompts without a paid request; conservative input guard, not a tokenizer")
    p.add_argument("--max-run-seconds", type=float, help="Stop between requests before the Slurm wall time limit")
    p.add_argument("--max-cost-usd", type=float,
                   help="Cumulative reported-cost stop line for this output directory; one in-flight request can exceed it")
    p.add_argument("--max-unconfirmed-requests", type=int, default=0,
                   help="Additional automatically reserved unknown-fee requests allowed across resumes; legacy explicit reservations remain separately accounted")
    p.add_argument("--prepare-resume", action="store_true",
                   help="Validate manifest and prepare unknown-fee reservations using public pricing; no key or paid request")
    p.add_argument("--model", help="Override the configured reference model explicitly")
    p.add_argument("--dry-run", action="store_true", help="Select/count only; no key, network, model, or API calls")
    p.add_argument("--check-model", action="store_true", help="Public model metadata only; no key or generation")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.max_unconfirmed_requests < 0:
        p.error("--max-unconfirmed-requests must be nonnegative")
    if args.prepare_resume and args.dry_run:
        p.error("Choose either --prepare-resume or --dry-run")
    if args.max_unconfirmed_requests and args.max_cost_usd is None:
        p.error("Unknown-fee allowance requires --max-cost-usd")
    if args.max_prompt_bytes < 1:
        p.error("--max-prompt-bytes must be positive")
    if args.limit_tasks is not None and args.limit_tasks < 1:
        p.error("--limit-tasks must be positive")
    if args.max_cost_usd is not None and (not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0):
        p.error("--max-cost-usd must be finite and positive")
    if args.max_run_seconds is not None and (not math.isfinite(args.max_run_seconds) or args.max_run_seconds <= 0):
        p.error("--max-run-seconds must be finite and positive")
    settings = load_settings(args.config)
    if args.model:
        settings.skill_extractor.model = args.model
    if args.output_dir:
        settings.paths.artifacts_dir = args.output_dir.expanduser().resolve()
    extractor = settings.skill_extractor
    if extractor.backend != "openai" or extractor.api_base != "https://openrouter.ai/api/v1":
        p.error("This entrypoint requires the configured OpenRouter API endpoint")
    if not extractor.structured_skill or settings.skill_build.schema_format != "compact":
        p.error("This entrypoint requires the compact structured skill schema")
    if args.check_model:
        print(json.dumps(check_model(settings), indent=2))
        return 0
    if not args.dry_run and not args.prepare_resume and not os.environ.get(extractor.api_key_env, "").strip():
        p.error(f"Set {extractor.api_key_env} in the environment; do not pass the key as a command argument")
    with output_lock(settings.paths.artifacts_dir):
        if args.dry_run:
            selected, tasks = prepare_skill_inputs(settings, limit=args.limit_tasks)
            result = {"dry_run": True, "tasks": len(tasks), "selected_trajectories": len(selected),
                      "model": extractor.model, "prompt_version": settings.skill_build.prompt_version,
                      "output_dir": str(settings.paths.artifacts_dir)}
        else:
            model_info = check_model(settings)
            ensure_run_manifest(settings)
            atomic_write_json(settings.paths.artifacts_dir / "model_check.json", model_info)
            estimate = reservation_estimate(model_info, extractor) if args.max_unconfirmed_requests else None
            policy = dict(max_unconfirmed_requests=args.max_unconfirmed_requests,
                          estimate=estimate, max_cost_usd=args.max_cost_usd)
            atomic_write_json(settings.paths.artifacts_dir / "unknown_cost_policy.json", policy)
            if args.prepare_resume:
                state, quarantined, over_limit = reserve_unknown_requests(
                    settings.paths.artifacts_dir, limit=args.max_unconfirmed_requests, estimate=estimate)
                result = dict(prepare_resume=True, paid_requests=0, policy=policy,
                              billing=state, quarantined_generation_ids=sorted(quarantined),
                              stopped=bool(state['unreserved_unknown_calls']) or over_limit)
                atomic_write_json(settings.paths.artifacts_dir / "resume_preparation.json", result)
                export_candidates(settings.paths.artifacts_dir)
            else:
                backend = create_chat_backend(settings, role="skill_extractor")
                try:
                    progress = ProgressBackend(backend, directory=settings.paths.artifacts_dir,
                                               max_cost_usd=args.max_cost_usd, max_run_seconds=args.max_run_seconds,
                                               max_prompt_bytes=args.max_prompt_bytes,
                                               max_unconfirmed_requests=args.max_unconfirmed_requests,
                                               unknown_estimate=estimate)
                    try:
                        progress.check_unknown_budget()
                        result = build_raw_candidates(settings, progress, limit=args.limit_tasks)
                        # Also stop if the final selected request exceeded the unknown allowance.
                        progress.check_unknown_budget()
                    except BudgetStop as exc:
                        result = {"stopped": True, "reason": str(exc)}
                    result["max_cost_usd"] = args.max_cost_usd
                    result["reported_cost_usd"] = progress.spent
                    result["reconciled_cost_usd"] = progress.reconciled
                    result["reserved_unconfirmed_cost_usd"] = progress.reserved
                    result["budget_accounted_usd"] = progress.spent + progress.reconciled + progress.reserved
                    result["max_prompt_bytes"] = args.max_prompt_bytes
                    result["max_unconfirmed_requests"] = args.max_unconfirmed_requests
                    atomic_write_json(settings.paths.artifacts_dir / "run_status.json", result)
                finally:
                    backend.close()
                    export_candidates(settings.paths.artifacts_dir)
            result["usage_summary"] = str(settings.paths.artifacts_dir / "usage_summary.json")
            result["candidate_skills"] = str(settings.paths.artifacts_dir / "candidate_skills.jsonl")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result.get("stopped") else (2 if result.get("failed_extractions", 0) else 0)


def entrypoint():
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Avoid dumping exception/HTTP request objects that could contain credentials.
        if isinstance(exc, RuntimeError) and str(exc).startswith(("Cannot read public", "Configured model", "Catalog ", "Prompt/model", "Existing extraction", "Another distillation", "Skill API request rejected", "Unresolved API attempts")):
            message = str(exc)
        else:
            message = "Check configuration, input files and durable extraction logs"
        print(f"{type(exc).__name__}: {message}", flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    entrypoint()
