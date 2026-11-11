"""Validate the new textual protocol with its enabled, effective tool schemas."""

import json
from typing import Any
from pydantic import TypeAdapter, ValidationError
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_action_protocol import PROTOCOL, validate_action
from lab_generate_skill.domain.actor_tool_definitions import TOOL_DEFINITIONS
from lab_generate_skill.domain.observation_read import (
    ObservationReadRequest,
    ListObservationRegions,
    ReadObservationRegions,
    SearchObservationRegions,
)
from lab_generate_skill.domain.observation_read_choice import (
    ActorObservationReadChoice,
    ListObservationChoice,
    ReadObservationChoice,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.actor_proposal_feedback import RejectionCode
from lab_generate_skill.policies.actor_tool_schemas import (
    materialize_actor_tools,
    ActorToolSchemas,
)
from lab_generate_skill.policies.actor_proposal_feedback import reject_proposal
from lab_generate_skill.policies.actor_proposal_syntax import (
    proposal_object,
    literal_action,
)
from .tool_schema_validation import actor_schema_violations

NEW_PROMPTS = ("browsergym-adaptive-full-ax-v2", "browsergym-adaptive-local-ax-v2")
_CHOICE: TypeAdapter[ActorObservationReadChoice] = TypeAdapter(
    ActorObservationReadChoice
)


def current_tool_schemas(
    prompt: ActorPrompt, actions: tuple[str, ...]
) -> ActorToolSchemas:
    view = prompt.observation_view
    if (
        prompt.prompt_version not in NEW_PROMPTS
        or view is None
        or view.schema_version != "actor-observation-view/3"
        or view.tab_count is None
    ):
        raise OwnershipConflict(
            "New proposal parser requires the exact explicit current view3"
        )
    return materialize_actor_tools(
        actions,
        view.tools,
        view.policy,
        view.snapshot.observation_ref.sha256,
        view.tab_count,
    )


def _validate(schema: dict[str, Any], value: Any, tool: str) -> None:
    errors = actor_schema_violations(schema, value)
    if not errors:
        return
    error = next(
        (
            item
            for item in errors
            if item.keyword == "pattern"
            and any(
                key in ("region_id", "region_ids", "parent_region_id")
                for key in item.path
            )
        ),
        errors[0],
    )
    actual = value
    for key in error.path:
        if isinstance(actual, dict) and key in actual:
            actual = actual[key]
        elif isinstance(actual, list) and isinstance(key, int) and key < len(actual):
            actual = actual[key]
        else:
            actual = None
            break
    field = ".".join(str(key) for key in error.path) or "arguments"
    if error.keyword == "pattern" and any(
        key in ("region_id", "region_ids", "parent_region_id") for key in error.path
    ):
        reject_proposal(
            "UNKNOWN_REGION",
            "This is not a region_id in the current captured index contract.",
            "Use exact region_ids from current public directory/search results; do not construct IDs or substitute element bids.",
            tool=tool,
            field=field,
            actual=actual,
            allowed="current public region_ids",
        )
    reject_proposal(
        "INVALID_ARGUMENTS",
        "A tool parameter does not match its current schema.",
        "Correct the indicated field using the enabled tool contract and current public example.",
        tool=tool,
        field=field,
        actual={"type": type(actual).__name__, "value": actual},
        allowed={error.keyword: error.allowed},
    )


def schema_action(
    value: dict[str, Any], task: PublicTask, schemas: ActorToolSchemas, action_id: str
) -> BrowserAction:
    if "action" not in value:
        reject_proposal(
            "WRONG_TOOL_BRANCH",
            "This is a read object, not a browser action.",
            "Use the registered read consumer; do not convert it into an action string.",
        )
    name, arguments = literal_action(
        value["action"],
        TOOL_DEFINITIONS,
        task.allowed_actions,
        tuple(
            tool["name"] for tool in schemas.tools if tool["kind"] == "observation_read"
        ),
    )
    _validate(
        schemas.require_tool(name, "browser_action")["inputSchema"], arguments, name
    )
    try:
        action = BrowserAction(
            action_id=action_id,
            protocol_id=PROTOCOL,
            name=name,
            payload=value["action"].strip(),
        )
    except ValidationError as error:
        issues = error.errors()
        if (
            len(issues) == 1
            and issues[0]["loc"] == ("payload",)
            and issues[0]["type"] == "string_too_long"
        ):
            reject_proposal(
                "INVALID_ARGUMENTS",
                "This action exceeds the existing BrowserAction payload limit.",
                "Shorten this single action; do not truncate or alter its meaning automatically.",
                tool=name,
                field="action",
                actual=len(value["action"].strip()),
                allowed=issues[0].get("ctx", {}).get("max_length"),
            )
        raise
    validate_action(action, task)
    return action


def schema_read(
    value: dict[str, Any],
    prompt: ActorPrompt,
    schemas: ActorToolSchemas,
    request_id: str,
) -> ObservationReadRequest | None:
    if "read" not in value:
        return None
    proposal = value["read"]
    view = prompt.observation_view
    assert view is not None
    if not isinstance(proposal, dict) or type(proposal.get("tool")) is not str:
        reject_proposal(
            "INVALID_ARGUMENTS",
            "read must be an object naming one registered tool.",
            "Use the current read object example.",
            field="read",
            actual=type(proposal).__name__,
        )
    tool = proposal["tool"]
    if tool not in view.tools:
        code: RejectionCode = (
            "WRONG_TOOL_BRANCH"
            if tool in TOOL_DEFINITIONS
            and TOOL_DEFINITIONS[tool]["kind"] == "browser_action"
            else "UNKNOWN_TOOL"
        )
        reject_proposal(
            code,
            "The selected tool is not a registered reader in this observation.",
            "Use the current enabled read tools; browser functions belong in action.",
            tool=tool,
            field="read.tool",
            actual=tool,
            allowed=view.tools,
        )
    ranges = proposal.get("ranges")
    if (
        tool == "read_region"
        and isinstance(ranges, list)
        and len(ranges) > view.policy.max_ranges
    ):
        reject_proposal(
            "RANGE_COUNT_EXCEEDED",
            f"Read not executed: submitted {len(ranges)} ranges; this request allows at most {view.policy.max_ranges}.",
            "Reduce the range count and use region_ids from current public results; list the directory first if needed.",
            tool=tool,
            field="ranges",
            actual=len(ranges),
            allowed=view.policy.max_ranges,
        )
    output = proposal.get("output_tokens")
    if type(output) is int and output > view.policy.body_max_tokens:
        reject_proposal(
            "OUTPUT_BUDGET_EXCEEDED",
            "Requested output exceeds the frozen body limit.",
            "Reduce output_tokens or continue using a valid issued cursor.",
            tool=tool,
            field="output_tokens",
            actual=output,
            allowed=view.policy.body_max_tokens,
        )
    snapshot = proposal.get("snapshot_sha256")
    if type(snapshot) is str and snapshot != view.snapshot.observation_ref.sha256:
        reject_proposal(
            "STALE_SNAPSHOT",
            "The proposal references a different public observation.",
            "Use snapshot_sha256 from the current observation; do not recover an old snapshot.",
            tool=tool,
            field="snapshot_sha256",
            actual=snapshot,
            allowed=view.snapshot.observation_ref.sha256,
        )
    _validate(
        schemas.require_tool(tool, "observation_read")["inputSchema"], proposal, tool
    )
    if isinstance(ranges, list):
        for item in ranges:
            if item.get("unit") != "whole_region" and item["start"] >= item["end"]:
                reject_proposal(
                    "RANGE_OUT_OF_BOUNDS",
                    "Range start must precede end.",
                    "Use a nonempty zero-based half-open range [start,end).",
                    tool=tool,
                    field="ranges",
                    actual=[item["start"], item["end"]],
                    allowed="start < end",
                )
    try:
        choice = _CHOICE.validate_json(
            json.dumps(proposal, ensure_ascii=False, allow_nan=False)
        )
    except ValidationError:
        reject_proposal(
            "INVALID_ARGUMENTS",
            "Reading fields violate the declared range contract.",
            "Use the current complete reading example and correct its range fields.",
            tool=tool,
            field="read",
        )
    base: dict[str, Any] = dict(
        request_id=request_id,
        snapshot=view.snapshot,
        output_tokens=choice.output_tokens,
        continuation=choice.continuation,
    )
    if isinstance(choice, ListObservationChoice):
        return ListObservationRegions(**base, parent_region_id=choice.parent_region_id)
    if isinstance(choice, ReadObservationChoice):
        return ReadObservationRegions(**base, ranges=choice.ranges)
    return SearchObservationRegions(
        **base, query=choice.query, mode=choice.mode, region_ids=choice.region_ids
    )


def parse_schema_proposal(
    text: str,
    finish_reason: str,
    task: PublicTask,
    prompt: ActorPrompt,
    *,
    action_id: str,
    request_id: str,
) -> BrowserAction | ObservationReadRequest:
    if (
        prompt.observation_view is None
        or prompt.observation_view.snapshot.scope.task != task.identity
    ):
        raise OwnershipConflict("Proposal parser changed its frozen public task")
    schemas = current_tool_schemas(prompt, task.allowed_actions)
    value = proposal_object(text, finish_reason)
    reading = schema_read(value, prompt, schemas, request_id)
    return (
        schema_action(value, task, schemas, action_id) if reading is None else reading
    )
