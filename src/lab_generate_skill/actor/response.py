"""Parse one baseline response without repair, a second request or code execution."""

import ast
import json
from lab_generate_skill.domain.actor_prompt import MAX_ACTOR_RESPONSE_BYTES
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_action_protocol import PROTOCOL, validate_action
from lab_generate_skill.domain.task import PublicTask
from .instructions import ACTIONS


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Actor response key")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError("Nonfinite Actor response value")


def parse_actor_action(
    text: str,
    finish_reason: str,
    task: PublicTask,
    action_id: str,
    *,
    prompt: ActorPrompt | None = None,
) -> BrowserAction:
    if prompt is not None:
        from .schema_response import current_tool_schemas, schema_action
        from lab_generate_skill.policies.actor_proposal_syntax import proposal_object

        return schema_action(
            proposal_object(text, finish_reason),
            task,
            current_tool_schemas(prompt, task.allowed_actions),
            action_id,
        )
    task = PublicTask.model_validate(task)
    if type(text) is not str or type(finish_reason) is not str:
        raise TypeError("Actor response and finish reason must be strings")
    if (
        finish_reason != "stop"
        or not 0 < len(text.encode()) <= MAX_ACTOR_RESPONSE_BYTES
    ):
        raise ValueError("Actor response unfinished, empty or outside byte budget")
    decoder = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=_constant)
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or set(value) - {"thought", "action"}:
            raise ValueError("Actor response has unsupported fields")
        payload = value.get("action")
        if type(payload) is not str:
            raise ValueError(
                "action must be one allowed BrowserGym function string; an observation read belongs in a separate read object, never mixed with action"
            )
        if not isinstance(value.get("thought", ""), str):
            raise ValueError("thought must be a string")
        tree = ast.parse(payload.strip(), mode="eval").body
        if (
            not isinstance(tree, ast.Call)
            or not isinstance(tree.func, ast.Name)
            or tree.func.id not in ACTIONS
        ):
            raise ValueError(
                "action must be one allowed BrowserGym function string. Observation tools are not browser actions; a registered observation tool requires its read object. This proposal was not executed."
            )
        action = BrowserAction(
            action_id=action_id,
            protocol_id=PROTOCOL,
            name=tree.func.id,
            payload=payload.strip(),
        )
        validate_action(action, task)
        return action
    raise ValueError("No valid JSON object in Actor response")
