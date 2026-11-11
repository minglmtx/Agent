"""One deterministic corrective example, shared by decisions and closed review."""

import json
import re
from typing import Any

from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.policies.actor_proposal_identity import (
    counted_proposal_feedback,
)
from lab_generate_skill.policies.actor_proposal_syntax import strict_proposal_json
from .schema_response import current_tool_schemas, parse_schema_proposal
from .tool_example_binding import (
    ExampleFacts,
    action_format_example,
    read_format_example,
)

EXAMPLE_MARKER = "Format example only (not executed; not a target recommendation): "
TEMPLATE_MARKER = "Non-executable format template (fill current public values; not validated against live state): "


def prompt_example_facts(prompt: ActorPrompt) -> ExampleFacts:
    assert prompt.observation_view is not None
    body = prompt.observation_view.body(prompt.messages[1].content)
    facts = ExampleFacts(body, None)
    for metadata in facts.metadata():
        overview = metadata.get("original_public_overview", metadata)
        if not isinstance(overview, dict):
            continue
        tabs = overview.get("tabs", [])
        active = overview.get("active_tab_id")
        if isinstance(tabs, list):
            for i, tab in enumerate(tabs):
                if (
                    isinstance(tab, dict)
                    and tab.get("tab_id") == active
                    and isinstance(tab.get("url"), str)
                ):
                    return ExampleFacts(body, tab["url"], i)
    return facts


def _proposal(completion: ActorTextCompletion) -> dict[str, Any]:
    try:
        value = strict_proposal_json(completion.text)
    except (ValueError, UnicodeError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def corrective_proposal_feedback(
    error: ActorProposalError,
    prompt: ActorPrompt,
    completion: ActorTextCompletion,
    task: PublicTask,
) -> ActorProposalFeedback:
    feedback = counted_proposal_feedback(error, prompt, completion)
    if not feedback.can_correct:
        return feedback  # Persist the terminal refusal with no continuation example.
    view = prompt.observation_view
    assert view is not None
    schemas = current_tool_schemas(prompt, task.allowed_actions)
    facts = prompt_example_facts(prompt)
    value = _proposal(completion)
    enabled = {
        item["name"]: item
        for item in schemas.tools
        if item["kind"] == "browser_action"
        or view.reads_used < view.policy.reads_per_observation
    }
    name = feedback.tool if feedback.tool in enabled else None
    if name is None:
        candidates = sorted(
            enabled,
            key=lambda item: (
                item != "click",
                item in ("send_msg_to_user", "report_infeasible"),
                item,
            ),
        )
        name = next(
            (
                item
                for item in candidates
                if enabled[item]["kind"] == "browser_action"
                and (item != "click" or facts.bids(clickable=True))
            ),
            candidates[0] if candidates else None,
        )
    if name is None:
        return feedback
    definition = enabled[name]
    fields: tuple[str, ...] = ()
    if definition["kind"] == "browser_action":
        payload = value.get("action", "")
        # Include submitted optional fields even when the call could not parse.
        submitted = (
            re.findall(r"(?:\(|,)\s*([A-Za-z_][A-Za-z_0-9]*)\s*[:=]", payload)
            if isinstance(payload, str)
            else []
        )
        fields = tuple(
            key
            for key in definition["argument_order"]
            if key in submitted or key == feedback.field
        )
        example, bound = action_format_example(
            name, task, schemas, facts, fields=fields
        )
    else:
        reading = value.get("read", {})
        ranges = reading.get("ranges", []) if isinstance(reading, dict) else []
        unit = (
            next(
                (
                    item.get("unit")
                    for item in ranges
                    if isinstance(item, dict)
                    and item.get("unit") in ("whole_region", "data_rows", "codepoints")
                ),
                "whole_region",
            )
            if isinstance(ranges, list)
            else "whole_region"
        )
        example, bound = read_format_example(
            name,
            schemas,
            facts,
            unit=str(unit),
            continuation=feedback.code == "INVALID_CONTINUATION",
            original_request=reading if isinstance(reading, dict) else None,
        )
    if bound:
        # The real parser validates the complete response without dispatching it.
        parse_schema_proposal(
            json.dumps(example),
            "stop",
            task,
            prompt,
            action_id="correction-format",
            request_id="correction-format",
        )
    text = feedback.next_action
    if name == feedback.tool:
        clauses = re.split(
            r"(?<=\.) |; ", definition["feedback"]["correction_template"]
        )
        matching = [
            clause
            for clause in clauses
            if any(field in clause for field in fields)
            or (feedback.field == "action" and "Keyword" in clause)
        ]
        if matching:
            text += " " + " ".join(matching)
    if name != feedback.tool:
        text += " The following illustrates another currently enabled reply format, not a replacement of your intent."
    text += (
        "\n"
        + (EXAMPLE_MARKER if bound else TEMPLATE_MARKER)
        + json.dumps(example, ensure_ascii=False, separators=(",", ":"))
    )
    return ActorProposalFeedback.model_validate(
        feedback.model_copy(update={"next_action": text})
    )


def correction_example(feedback: ActorProposalFeedback) -> dict[str, Any] | None:
    """Extract only this renderer's one complete example from retained facts."""
    for marker in (EXAMPLE_MARKER, TEMPLATE_MARKER):
        if marker in feedback.next_action:
            value = json.loads(feedback.next_action.split(marker, 1)[1])
            return value if isinstance(value, dict) else None
    return None
