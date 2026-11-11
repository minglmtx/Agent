from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import cached_text
from .schemas import TrajectoryRecord


def compact_trajectory(trace: TrajectoryRecord, *, max_message_chars: int = 6000) -> dict[str, Any]:
    compact_messages: list[dict[str, Any]] = []
    for message in trace.messages:
        if message.role == "system":
            continue
        content = message.content
        if len(content) > max_message_chars:
            content = content[:max_message_chars] + "\n[TRUNCATED_FOR_DISTILLATION_PROMPT]"
        compact_messages.append(
            {
                "turn": message.turn,
                "role": message.role,
                "content": content,
                "action_kind": message.action_kind,
                "action_payload": message.action_payload,
            }
        )
    return {
        "trace_id": trace.trace_id,
        "rollout_index": trace.rollout_index,
        "task_instruction": trace.task_instruction,
        "benchmark_skill_tags": trace.benchmark_skill_tags,
        "sample_status": trace.sample_status,
        "evaluation_outcome": trace.evaluation_outcome,
        "finish_reason": trace.finish_reason,
        "task_output": trace.task_output,
        "rounds": trace.rounds,
        "generation_finish_reasons": trace.generation_finish_reasons,
        "error": trace.error.model_dump(mode="json") if trace.error else None,
        "interaction": compact_messages,
    }


def render_skill_prompt(
    template_path: str | Path,
    *,
    traces: list[TrajectoryRecord],
    prompt_version: str,
    max_skills: int,
) -> str:
    if not traces:
        raise ValueError("Cannot render a skill prompt without trajectories")
    domain = traces[0].domain
    task_id = traces[0].task_id
    if any(trace.domain != domain or trace.task_id != task_id for trace in traces):
        raise ValueError("A distillation prompt must contain one domain/task group")
    template = cached_text(str(Path(template_path)))
    evidence = [compact_trajectory(trace) for trace in traces]
    if prompt_version.startswith("gobrowse-compact"):
        evidence = [{"domain": trace.domain, "task_instruction": trace.task_instruction,
                     "success": trace.succeeded, "task_output": trace.task_output,
                     "outcome_source": trace.provenance.get("outcome_source"),
                     "terminal_observation_available": trace.provenance.get("terminal_observation_available"),
                     "messages": [m.model_dump(mode="json") for m in trace.messages if m.role != "system"]}
                    for trace in traces]
    replacements = {
        "{{DOMAIN}}": domain,
        "{{TASK_ID}}": task_id,
        "{{PROMPT_VERSION}}": prompt_version,
        "{{TRAJECTORIES_JSON}}": json.dumps(evidence, ensure_ascii=False, indent=2),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    unresolved = [marker for marker in replacements if marker in template]
    if unresolved:
        raise ValueError(f"Unresolved prompt markers: {unresolved}")
    return template


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object, tolerating Qwen thinking/code-fence text."""

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("No valid JSON object found in model response")
