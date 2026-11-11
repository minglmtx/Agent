"""Pure response decoding with exact nanodollar accounting, never rounding."""

from lab_generate_skill.domain.model_request import ResolvedModelRequest
from lab_generate_skill.domain.model_response import ProviderReply
from lab_generate_skill.adapters.processes.wire_json import json_object
from .provider_charge import exact_charge


def decode_openrouter(request: ResolvedModelRequest, raw: bytes) -> ProviderReply:
    value = json_object(raw, exact_numbers=True)
    if "error" in value:
        raise ValueError("Provider reported an error inside its response")
    provider_id = value.get("id")
    choices = value.get("choices")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("Provider response has no identity")
    if (
        not isinstance(choices, list)
        or len(choices) != 1
        or not isinstance(choices[0], dict)
    ):
        raise ValueError("Expected exactly one completion")
    choice = choices[0]
    if choice.get("finish_reason") not in {
        "stop",
        "length",
        "tool_calls",
        "content_filter",
    }:
        raise ValueError("Response does not identify a completed generation")
    message = choice.get("message")
    if (
        not isinstance(message, dict)
        or message.get("role") != "assistant"
        or not (
            isinstance(message.get("content"), str)
            or isinstance(message.get("tool_calls"), list)
            and bool(message["tool_calls"])
        )
    ):
        raise ValueError("Completed response has no assistant output")
    usage = value.get("usage")
    charge = exact_charge(usage.get("cost") if isinstance(usage, dict) else None)
    return ProviderReply(
        request_id=request.request.request_id,
        provider_request_id=provider_id,
        raw_response=raw,
        charge=charge,
    )
