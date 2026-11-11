"""Exact rejected-operation identity; never infers equivalence from prose."""

import ast
import hashlib
import json
from typing import Any
from .actor_proposal_syntax import strict_proposal_json
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.domain.actor_tool_definitions import TOOL_DEFINITIONS
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
)


def _literal_identity(value: Any) -> Any:
    kind = type(value).__name__
    if isinstance(value, str):
        return [kind, value.encode("utf-8", errors="surrogatepass").hex()]
    if isinstance(value, bytes):
        return [kind, value.hex()]
    if type(value) is float:
        return [kind, value.hex()]
    if type(value) is complex:
        return [kind, value.real.hex(), value.imag.hex()]
    if isinstance(value, dict):
        pairs = [
            [_literal_identity(key), _literal_identity(item)]
            for key, item in value.items()
        ]
        return [
            kind,
            sorted(pairs, key=lambda pair: json.dumps(pair[0], sort_keys=True)),
        ]
    if isinstance(value, (list, tuple, set)):
        items = [_literal_identity(item) for item in value]
        return [
            kind,
            (
                sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
                if isinstance(value, set)
                else items
            ),
        ]
    return [kind, value] if value is None or type(value) in (bool, int) else [kind]


def _action_identity(payload: str) -> Any:
    try:
        call = ast.parse(payload.strip(), mode="eval").body
    except (SyntaxError, ValueError, RecursionError):
        return {"invalid_action_syntax": payload}
    try:
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            definition = TOOL_DEFINITIONS.get(call.func.id)
            if definition is not None and definition.get("kind") == "browser_action":
                order = definition["argument_order"]
                if len(call.args) > len(order):
                    raise ValueError("Too many positional arguments")
                arguments = {
                    name: _literal_identity(ast.literal_eval(node))
                    for name, node in zip(order, call.args)
                }
                for keyword in call.keywords:
                    if keyword.arg is None or keyword.arg in arguments:
                        raise ValueError("Duplicate or unpacked keyword")
                    arguments[keyword.arg] = _literal_identity(
                        ast.literal_eval(keyword.value)
                    )
                return {"tool": call.func.id, "arguments": arguments}
            return {
                "tool": call.func.id,
                "positional": [
                    _literal_identity(ast.literal_eval(arg)) for arg in call.args
                ],
                "keywords": sorted(
                    [
                        [key.arg, _literal_identity(ast.literal_eval(key.value))]
                        for key in call.keywords
                    ],
                    key=lambda pair: str(pair[0]),
                ),
            }
        return {"literal_action": _literal_identity(ast.literal_eval(call))}
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return {"invalid_action_ast": ast.dump(call, include_attributes=False)}


def proposal_fingerprint(
    prompt: ActorPrompt, completion: ActorTextCompletion, code: str
) -> str:
    view = prompt.observation_view
    if view is None:
        raise ValueError("Original bound observation is required for proposal identity")
    raw_sha = hashlib.sha256(
        completion.text.encode("utf-8", errors="surrogatepass")
    ).hexdigest()
    try:
        value = strict_proposal_json(completion.text)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raw: Any = {"raw_sha256": raw_sha}
    else:
        raw = (
            {key: item for key, item in value.items() if key != "thought"}
            if isinstance(value, dict)
            else value
        )
        if isinstance(value, dict) and isinstance(value.get("action"), str):
            raw = {
                "action": _action_identity(value["action"]),
                "extra_fields": {
                    key: item
                    for key, item in value.items()
                    if key not in ("action", "thought")
                },
            }
    encoded = json.dumps(
        [view.snapshot.model_dump(mode="json"), code, raw],
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(encoded).hexdigest()


def counted_proposal_feedback(
    error: ActorProposalError, prompt: ActorPrompt, completion: ActorTextCompletion
) -> ActorProposalFeedback:
    view = prompt.observation_view
    if view is None or view.invalid_proposals is None:
        raise ValueError("New feedback requires original verified rejection facts")
    policy, progress = view.policy, view.invalid_proposals
    if (
        policy.max_consecutive_invalid_proposals is None
        or policy.max_identical_invalid_proposals is None
    ):
        raise ValueError("Both frozen invalid-proposal limits are mandatory")
    signature = proposal_fingerprint(prompt, completion, error.feedback.code)
    consecutive = progress.consecutive_invalid + 1
    repeated = dict(progress.fingerprints).get(signature, 0) + 1
    can_correct = (
        consecutive < policy.max_consecutive_invalid_proposals
        and repeated < policy.max_identical_invalid_proposals
    )
    notice = ""
    if can_correct:
        if policy.max_identical_invalid_proposals - repeated == 1:
            notice = " Another identical invalid proposal will stop this run."
        elif policy.max_consecutive_invalid_proposals - consecutive == 1:
            notice = " Another invalid proposal will stop this run."
    next_action = (
        error.feedback.next_action + notice
        if can_correct
        else "Stop: the frozen invalid-proposal limit was reached; no action/read was executed."
    )
    return ActorProposalFeedback.model_validate(
        error.feedback.model_copy(
            update=dict(
                consecutive_invalid=consecutive,
                repeated_invalid=repeated,
                can_correct=can_correct,
                next_action=next_action,
            )
        )
    )
