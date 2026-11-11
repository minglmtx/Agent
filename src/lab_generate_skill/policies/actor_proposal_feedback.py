"""Bound confirmed proposal errors without echoing an entire model response."""

from typing import Any, NoReturn
import math
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
    RejectionCode,
)


def bounded_proposal_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return (
            value
            if len(value) <= 128
            else {"type": "string", "length": len(value), "prefix": value[:128]}
        )
    if isinstance(value, (list, tuple)):
        return (
            {"type": "array", "length": len(value)}
            if depth >= 2
            else [bounded_proposal_value(item, depth + 1) for item in value[:8]]
        )
    if isinstance(value, dict):
        return (
            {"type": "object", "fields": len(value)}
            if depth >= 2
            else {
                str(key)[:128]: bounded_proposal_value(item, depth + 1)
                for key, item in list(value.items())[:8]
            }
        )
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return (
            value if math.isfinite(value) else {"type": "float", "value": "nonfinite"}
        )
    return {"type": type(value).__name__}


def reject_proposal(
    code: RejectionCode,
    message: str,
    next_action: str,
    *,
    tool: str | None = None,
    field: str | None = None,
    actual: Any = None,
    allowed: Any = None,
) -> NoReturn:
    raise ActorProposalError(
        ActorProposalFeedback(
            code=code,
            message=message,
            next_action=next_action,
            tool=tool[:128] if tool is not None else None,
            field=field[:256] if field is not None else None,
            actual=bounded_proposal_value(actual),
            allowed=bounded_proposal_value(allowed),
        )
    )
