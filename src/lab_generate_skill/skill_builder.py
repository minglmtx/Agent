from __future__ import annotations

from collections import defaultdict
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .io_utils import append_jsonl, atomic_write_json, iter_jsonl
from .llm import ChatBackend, exception_diagnostics
from .prompting import parse_json_object, render_skill_prompt
from .schemas import CompactSkill, RawCandidateEnvelope, RawGenerationEnvelope, TrajectoryRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trajectory_groups(settings: Settings) -> dict[tuple[str, str], list[TrajectoryRecord]]:
    groups: dict[tuple[str, str], list[TrajectoryRecord]] = defaultdict(list)
    for domain in settings.collection.domains:
        path = settings.paths.trajectories_dir / f"{domain}.jsonl"
        for raw in iter_jsonl(path):
            trace = TrajectoryRecord.model_validate(raw)
            groups[(trace.domain, trace.task_id)].append(trace)

    expected = settings.collection.rollouts_per_task
    for key, traces in groups.items():
        by_index = {trace.rollout_index: trace for trace in traces}
        if len(by_index) != len(traces):
            raise ValueError(f"Duplicate rollout indices in task {key}")
        required = set(range(expected))
        missing = sorted(required.difference(by_index))
        if missing and settings.skill_build.selection != "outcome_balanced":
            raise ValueError(
                f"Task group {key} is incomplete: missing rollout indices {missing}; "
                f"expected exactly {expected} online rollouts per task"
            )
        groups[key] = [by_index[index] for index in sorted(by_index)]
    return dict(groups)


def _read_optional(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path)) if path.exists() else []


def _reservoir(items, capacity, rng):
    """Same Algorithm R as generative_skill's preparation script."""
    chosen = []
    for seen, item in enumerate(items, 1):
        if len(chosen) < capacity:
            chosen.append(item)
        else:
            index = rng.randrange(seen)
            if index < capacity:
                chosen[index] = item
    return chosen


def select_trajectories(settings: Settings, traces: list[TrajectoryRecord], *, rng=None):
    valid = [trace for trace in traces
             if trace.error is None and not trace.quality_flags and trace.evaluation_outcome in {"correct", "incorrect"}]
    positive = sorted((t for t in valid if t.succeeded), key=lambda t: t.rollout_index)
    negative = sorted((t for t in valid if not t.succeeded), key=lambda t: t.rollout_index)
    paired = bool(positive and negative)
    if settings.skill_build.selection == "outcome_balanced":
        rng = rng if rng is not None else random.Random(settings.collection.base_seed)
        successes = _reservoir(positive, 2, rng)
        failures = _reservoir(negative, 2, rng)
        selected_positive = successes[:1]
        selected_negative = failures[:1]
        remaining = 2 - len(selected_positive) - len(selected_negative)
        selected_positive += successes[len(selected_positive):len(selected_positive) + remaining]
        remaining = 2 - len(selected_positive) - len(selected_negative)
        selected_negative += failures[len(selected_negative):len(selected_negative) + remaining]
        selected = selected_positive + selected_negative
    elif settings.skill_build.selection == "outcome_pair":
        selected = positive[:1] + negative[:1]
        if settings.skill_build.require_outcome_pair and not paired:
            selected = []
    else:
        selected = valid if settings.skill_build.include_failed_trajectories else positive
    return selected, {
        "available_positive": len(positive), "available_negative": len(negative),
        "excluded_invalid": len(traces) - len(valid), "paired": paired,
        "missing_outcomes": (["correct"] if not positive else []) + (["incorrect"] if not negative else []),
        "selected_trace_ids": [t.trace_id for t in selected],
        "selected_positive": sum(t.succeeded for t in selected),
        "selected_negative": sum(not t.succeeded for t in selected),
        "same_outcome_fallback": bool(selected) and not paired,

    }


def _parse_candidate(settings: Settings, text: str, finish_reason: str | None):
    if finish_reason in {"length", "max_tokens"}:
        raise ValueError("generation_truncated")
    payload = parse_json_object(text)
    if settings.skill_build.schema_format == "compact":
        # Strict JSON object: reject explanatory text and wrappers as well as missing fields.
        import json
        candidate = CompactSkill.model_validate(json.loads(text)).model_dump()
    else:
        skills = payload.get("skills")
        if not isinstance(skills, list) or len(skills) != 1 or not isinstance(skills[0], dict):
            raise ValueError("Expected exactly one skill per trajectory")
        candidate = skills[0]
    from .postprocess import _contains_truncated_text
    if _contains_truncated_text(candidate):
        raise ValueError("candidate_contains_truncated_text")
    return candidate


def prepare_skill_inputs(settings: Settings, *, limit: int | None = None):
    """Write a deterministic selection report without initializing any model/API."""
    groups = load_trajectory_groups(settings)
    artifacts = settings.paths.artifacts_dir
    ordered = sorted(groups.items())
    if limit is not None:
        ordered = ordered[:limit]
    selections = []
    selected_traces = []
    rng = random.Random(settings.collection.base_seed)
    for (domain, task_id), traces in ordered:
        selected, report = select_trajectories(settings, traces, rng=rng)
        selections.append({"domain": domain, "task_id": task_id, **report})
        selected_traces.extend(selected)
    atomic_write_json(artifacts / "selection_report.json", {
        "selection": settings.skill_build.selection,
        "require_outcome_pair": settings.skill_build.require_outcome_pair,
        "tasks": selections, "selected_trajectories": len(selected_traces),
        "paired_tasks": sum(row["paired"] for row in selections),
        "fallback_tasks": sum(row["same_outcome_fallback"] for row in selections),
    })
    return selected_traces, selections


def build_raw_candidates(settings: Settings, backend: ChatBackend, *, limit: int | None = None) -> dict[str, int]:
    """Select source trajectories, then extract one skill from each trace.

    Raw generations form the durable API ledger. Valid responses can be replayed
    after an interruption without making another paid request.
    """
    artifacts = settings.paths.artifacts_dir
    generation_path = artifacts / "raw_generations.jsonl"
    candidate_path = artifacts / "raw_candidates.jsonl"
    completed = {row["generation_id"] for row in _read_optional(candidate_path)}
    historical = {}
    for row in _read_optional(generation_path):
        historical.setdefault(row["generation_id"], []).append(row)
    # Reserve each attempt durably BEFORE contacting the provider. A process kill
    # must not grant a fresh allowance on resume.
    request_path = artifacts / "request_attempts.jsonl"
    started = _read_optional(request_path)
    finished = {(r["generation_id"], r.get("attempt", 1))
                for records in historical.values() for r in records}
    unresolved = {(r["generation_id"], r["attempt"]) for r in started} - finished
    if unresolved:
        raise RuntimeError("Unresolved API attempts: reconcile provider billing before resuming")
    selected_traces, selections = prepare_skill_inputs(settings, limit=limit)
    excluded = {r["trace_id"] for r in _read_optional(artifacts / "excluded_inputs.jsonl")}
    generated = candidates = failed = recovered = skipped = quarantined = 0
    skipped_path = artifacts / "skipped_inputs.jsonl"
    skipped_keys = {(r['generation_id'], r.get('limit_bytes'))
                    for r in _read_optional(skipped_path)}
    for trace in selected_traces:
        generation_id = f"generation:{settings.skill_build.prompt_version}:{trace.trace_id}"
        if generation_id in completed:
            continue
        if trace.trace_id in excluded:
            skipped += 1
            continue
        def save_candidate(candidate, record):
            nonlocal candidates
            envelope = RawCandidateEnvelope(
                generation_id=generation_id, candidate_index=0, domain=trace.domain,
                task_id=trace.task_id, trace_ids=[trace.trace_id],
                prompt_version=settings.skill_build.prompt_version,
                generator_backend=record["generator_backend"], generator_model=record["generator_model"],
                generated_at=record["generated_at"], finish_reason=record["finish_reason"], candidate=candidate,
                length_check=CompactSkill.model_validate(candidate).length_report() if settings.skill_build.schema_format=="compact" else None)
            append_jsonl(candidate_path, [envelope.model_dump(mode="json")])
            completed.add(generation_id)
            candidates += 1

        # Recover the gap between durable response logging and candidate writing.
        for record in reversed(historical.get(generation_id, [])):
            if record.get("parse_error"):
                continue
            try:
                candidate = _parse_candidate(settings, record["response_text"], record["finish_reason"])
            except (ValueError, TypeError):
                continue
            save_candidate(candidate, record)
            recovered += 1
            break
        if generation_id in completed:
            continue
        if getattr(backend, 'is_quarantined', lambda _: False)(generation_id):
            quarantined += 1
            continue
        previous = historical.get(generation_id, [])
        used = max([len(previous)] + [r.get("attempt", 1) for r in previous])
        if used >= settings.skill_build.max_attempts:
            failed += 1
            continue
        prompt = render_skill_prompt(settings.paths.prompt_template, traces=[trace],
            prompt_version=settings.skill_build.prompt_version, max_skills=1)
        messages = [{"role": "system", "content": "Extract one grounded reusable skill. Return strict JSON."},
                    {"role": "user", "content": prompt}]
        check_input = getattr(backend, "check_input", None)
        input_issue = check_input(messages) if check_input is not None else None
        if input_issue:
            key = (generation_id, input_issue.get('limit_bytes'))
            if key not in skipped_keys:
                append_jsonl(skipped_path, [{"generation_id": generation_id, "trace_id": trace.trace_id,
                    "task_id": trace.task_id, "domain": trace.domain, "checked_at": _utc_now(),
                    "api_request_sent": False, **input_issue}])
                skipped_keys.add(key)
            skipped += 1
            continue
        for attempt in range(used + 1, settings.skill_build.max_attempts + 1):
            before_request = getattr(backend, "before_request", None)
            if before_request is not None:
                before_request()
            append_jsonl(request_path, [{"generation_id": generation_id,
                                        "attempt": attempt, "started_at": _utc_now()}])
            result = None
            candidate = None
            error = None
            fatal = None
            diagnostics = None
            started_at = time.monotonic()
            try:
                result = backend.generate(messages, seed=trace.seed)
                candidate = _parse_candidate(settings, result.text, result.finish_reason)
            except Exception as exc:
                # Do not persist exception text: upstream errors can contain request secrets.
                diagnostics = exception_diagnostics(exc)
                result = getattr(exc, "generation_result", result)
                status = getattr(exc, "status_code", None)
                error = f"{type(exc).__name__}" + (f": HTTP {status}" if status else "")
                if status is not None and status not in {408, 409, 429} and status < 500:
                    fatal = RuntimeError(f"Skill API request rejected (HTTP {status}); check model/access/configuration")
            record = RawGenerationEnvelope(
                generation_id=generation_id, domain=trace.domain, task_id=trace.task_id,
                trace_ids=[trace.trace_id], prompt_version=settings.skill_build.prompt_version,
                generator_backend=backend.name, generator_model=backend.model_name,
                generated_at=_utc_now(), finish_reason=result.finish_reason if result else None,
                response_text=result.text if result else "", parse_error=error,
                attempt=attempt,
                prompt_tokens=result.prompt_tokens if result else None,
                completion_tokens=result.completion_tokens if result else None,
                reasoning_tokens=result.reasoning_tokens if result else None,
                cost=result.cost if result else None,
                billing_status='not_sent' if diagnostics and diagnostics['request_not_sent'] else None,
                error_diagnostics=diagnostics,
                elapsed_seconds=round(time.monotonic() - started_at, 3),
                provider_request_id=(result.provider_request_id if result else None)
                    or (diagnostics['provider_request_id'] if diagnostics else None),
                provider_response_id=result.provider_response_id if result else None,
                api_error_type=result.api_error_type if result else None,
                api_error_code=result.api_error_code if result else None,
            ).model_dump(mode="json")
            append_jsonl(generation_path, [record])
            generated += 1
            after_record = getattr(backend, 'after_record', None)
            if after_record is not None:
                after_record(record)
            if fatal:
                raise fatal
            if candidate is not None:
                save_candidate(candidate, record)
                break
            if getattr(backend, 'is_quarantined', lambda _: False)(generation_id):
                quarantined += 1
                break
            if attempt < settings.skill_build.max_attempts:
                time.sleep(min(2 ** (attempt - 1), 16))
        if generation_id not in completed:
            failed += 1
    return {"generations": generated, "candidates": candidates, "failed_extractions": failed,
            "quarantined_billing": quarantined, "recovered_candidates": recovered, "skipped_inputs": skipped, "selected_trajectories": len(selected_traces),
            "paired_tasks": sum(row["paired"] for row in selections),
        "fallback_tasks": sum(row["same_outcome_fallback"] for row in selections),
            "unpaired_tasks": sum(not row["paired"] for row in selections)}
