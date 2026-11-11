"""Strict JSON and safe literal argument binding for the explicit new protocol."""

import ast
import json
import math
import re
from typing import Any
from lab_generate_skill.domain.actor_prompt import MAX_ACTOR_RESPONSE_BYTES
from lab_generate_skill.domain.actor_proposal_feedback import ActorProposalError
from .actor_proposal_feedback import reject_proposal


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON key")
        result[name] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("Nonfinite JSON number")


def strict_proposal_json(text: str) -> Any:
    """Shared with fingerprints; malformed JSON keeps its original raw digest."""
    raw = text.encode("utf-8")
    if not 0 < len(raw) <= MAX_ACTOR_RESPONSE_BYTES:
        raise ValueError("Response is empty or exceeds its byte boundary")
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("Nonfinite JSON number")
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def proposal_object(text: str, finish_reason: str) -> dict[str, Any]:
    if type(text) is not str or type(finish_reason) is not str:
        raise TypeError("Actual response text and finish reason must be strings")
    if finish_reason != "stop":
        reject_proposal(
            "INVALID_RESPONSE_SHAPE",
            "The response did not finish with stop.",
            "Return one complete JSON object within the output budget.",
            actual=finish_reason,
            allowed="stop",
        )
    try:
        value = strict_proposal_json(text)
    except (ValueError, UnicodeError, RecursionError):
        reject_proposal(
            "INVALID_JSON",
            "Expected one complete UTF-8 JSON object with unique keys and finite numbers.",
            "Return JSON only, with exactly one action or read; remove duplicate keys and trailing text.",
        )
    if (
        not isinstance(value, dict)
        or set(value)
        not in ({"action"}, {"thought", "action"}, {"read"}, {"thought", "read"})
        or type(value.get("thought", "")) is not str
    ):
        reject_proposal(
            "INVALID_RESPONSE_SHAPE",
            "The reply must contain exactly one action or read, optionally thought.",
            "Use the current complete format example; remove extra fields or the other branch.",
            allowed=["thought + action", "thought + read"],
        )
    return value


def _misplaced_read(
    payload: Any, tree: ast.expr | None, definitions: dict[str, Any]
) -> str | None:
    value = payload
    if isinstance(payload, str):
        try:
            value = strict_proposal_json(payload)
        except (ValueError, UnicodeError, RecursionError):
            try:
                value = ast.literal_eval(tree) if tree is not None else None
            except (ValueError, TypeError, SyntaxError, RecursionError):
                value = None
    if (
        isinstance(value, dict)
        and set(value) == {"read"}
        and isinstance(value["read"], dict)
    ):
        value = value["read"]
    if (
        isinstance(value, (list, tuple))
        and len(value) == 1
        and isinstance(value[0], dict)
    ):
        value = value[0]
    if isinstance(tree, (ast.List, ast.Tuple)) and len(tree.elts) == 1:
        tree = tree.elts[0]
    names: list[Any] = []
    if isinstance(value, dict):
        names.extend(value.get(key) for key in ("tool", "name"))
        if len(value) == 1:
            names.extend(value.keys())
    if isinstance(tree, ast.Name):
        names.append(tree.id)
    if isinstance(tree, ast.Call):
        if isinstance(tree.func, ast.Name):
            names.append(tree.func.id)
        elif isinstance(tree.func, ast.Attribute):
            names.append(tree.func.attr)
    return next(
        (
            name
            for name in names
            if isinstance(name, str)
            and name in definitions
            and definitions[name]["kind"] == "observation_read"
        ),
        None,
    )


def literal_action(
    payload: Any,
    definitions: dict[str, Any],
    enabled: tuple[str, ...],
    reads: tuple[str, ...] = (),
) -> tuple[str, dict[str, Any]]:
    direct = _misplaced_read(payload, None, definitions)
    if direct is not None:
        reject_proposal(
            "WRONG_TOOL_BRANCH" if direct in reads else "UNKNOWN_TOOL",
            "A reading tool was placed in action; this proposal was not executed.",
            (
                "Put this registered tool and its fields in a read object."
                if direct in reads
                else "Use only tools registered in the current observation."
            ),
            tool=direct,
            field="action",
        )
    if type(payload) is not str:
        reject_proposal(
            "INVALID_ARGUMENTS",
            "action must be a function-call string.",
            "Use one enabled browser function with literal arguments.",
            field="action",
            actual=type(payload).__name__,
            allowed="string",
        )
    try:
        call = ast.parse(payload.strip(), mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        # Recognize only the literal leading declared name; never repair or run it.
        match = re.match(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*\(", payload)
        name = match.group(1) if match and match.group(1) in enabled else None
        reject_proposal(
            "INVALID_ARGUMENTS",
            "action is not one valid function call.",
            "Use one literal function call; keyword arguments use name=value, never name:value.",
            tool=name,
            field="action",
        )
    misplaced = _misplaced_read(payload, call, definitions)
    if misplaced is not None:
        reject_proposal(
            "WRONG_TOOL_BRANCH" if misplaced in reads else "UNKNOWN_TOOL",
            "A reading tool was placed in action; this proposal was not executed.",
            (
                "Put this registered tool and its fields in a read object."
                if misplaced in reads
                else "Use only tools registered in the current observation."
            ),
            tool=misplaced,
            field="action",
        )
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        reject_proposal(
            "INVALID_ARGUMENTS",
            "One named browser function call is required.",
            "Remove expressions, attribute access and additional statements.",
            field="action",
        )
    name = call.func.id
    definition = definitions.get(name)
    if definition is not None and definition["kind"] == "observation_read":
        reject_proposal(
            "WRONG_TOOL_BRANCH",
            "A reading tool cannot be placed in action.",
            "Put the registered reading tool and its fields in a read object.",
            tool=name,
            field="action",
        )
    if definition is None or name not in enabled:
        reject_proposal(
            "UNKNOWN_TOOL",
            "This browser tool is not enabled for the current task.",
            "Select an enabled tool from the current contract.",
            tool=name,
            actual=name,
            allowed=enabled,
        )
    order = definition["argument_order"]
    if (
        len(call.args) > len(order)
        or any(isinstance(arg, ast.Starred) for arg in call.args)
        or any(key.arg is None for key in call.keywords)
    ):
        reject_proposal(
            "INVALID_ARGUMENTS",
            "Too many positional arguments or unpacking is not allowed.",
            "Bind each declared parameter once using literal arguments.",
            tool=name,
            field="arguments",
            allowed=order,
        )
    arguments = {}
    try:
        for key, node in zip(order, call.args):
            arguments[key] = ast.literal_eval(node)
        for keyword in call.keywords:
            assert keyword.arg is not None
            if keyword.arg in arguments:
                reject_proposal(
                    "INVALID_ARGUMENTS",
                    "A parameter was bound more than once.",
                    "Supply each positional or keyword parameter once.",
                    tool=name,
                    field=keyword.arg,
                )
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        pending = list(arguments.values())
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, (list, tuple, set)):
                pending.extend(value)
    except ActorProposalError:
        raise
    except (ValueError, TypeError, SyntaxError, RecursionError, UnicodeError):
        reject_proposal(
            "INVALID_ARGUMENTS",
            "Function arguments must be literal values.",
            "Remove expressions, calls and unpacking from arguments.",
            tool=name,
            field="arguments",
        )
    return name, arguments
