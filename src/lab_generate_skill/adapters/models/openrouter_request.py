"""Pure OpenRouter request projection; preserve frozen sampling/provider policy."""

import json
from lab_generate_skill.domain.model_request import ResolvedModelRequest
from lab_generate_skill.adapters.processes.wire_json import json_object


def prepare_openrouter(request: ResolvedModelRequest) -> bytes:
    request = ResolvedModelRequest.model_validate(request)
    if request.request.provider_id != "openrouter":
        raise ValueError("This transport requires the frozen OpenRouter provider")
    inputs, parameters = json_object(request.input_bytes), json_object(
        request.parameters_bytes
    )
    if set(inputs) != {"messages"}:
        raise ValueError("Model input must contain only approved messages")
    messages = inputs["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError("At least one chat message is required")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {
            "system",
            "developer",
            "user",
            "assistant",
            "tool",
        }:
            raise ValueError("Invalid chat message")
        if set(message) - {
            "role",
            "content",
            "name",
            "tool_calls",
            "tool_call_id",
            "reasoning_details",
        }:
            raise ValueError("Unsupported message fields require a protocol revision")
        content = message.get("content")
        if not isinstance(content, (str, list)) and not (
            content is None
            and message["role"] == "assistant"
            and message.get("tool_calls")
        ):
            raise ValueError("Chat message has no supported content")
        if isinstance(content, list):
            if not content:
                raise ValueError("Empty multipart message")
            for part in content:
                if not isinstance(part, dict) or part.get("type") not in {
                    "text",
                    "image_url",
                }:
                    raise ValueError("Unsupported multipart message")
                if part["type"] == "text":
                    if set(part) != {"type", "text"} or not isinstance(
                        part["text"], str
                    ):
                        raise ValueError("Invalid text content part")
                elif (
                    set(part) != {"type", "image_url"}
                    or not isinstance(part["image_url"], dict)
                    or (
                        not isinstance(part["image_url"].get("url"), str)
                        or not part["image_url"]["url"]
                    )
                ):
                    raise ValueError("Invalid image content part")
    allowed = {
        "max_tokens",
        "seed",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "top_a",
        "frequency_penalty",
        "presence_penalty",
        "repetition_penalty",
        "stop",
        "reasoning",
        "response_format",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "provider",
    }
    if set(parameters) - allowed:
        raise ValueError("Unsupported parameters or attempted routing/model override")
    if type(parameters.get("max_tokens")) is not int or parameters["max_tokens"] <= 0:
        raise ValueError("A positive frozen output token bound is required")
    provider = parameters.get("provider")
    if not isinstance(provider, dict) or provider.get("allow_fallbacks") is not False:
        raise ValueError("Frozen provider policy must explicitly disable fallbacks")
    if provider.get("require_parameters") is not True:
        raise ValueError("Frozen provider policy must require supported parameters")
    if set(provider) - {
        "allow_fallbacks",
        "require_parameters",
        "sort",
        "order",
        "only",
        "ignore",
        "max_price",
        "data_collection",
        "zdr",
    }:
        raise ValueError("Unsupported provider policy fields")
    for name in ("order", "only", "ignore"):
        if name in provider and (
            not isinstance(provider[name], list)
            or not provider[name]
            or any(not isinstance(x, str) or not x.strip() for x in provider[name])
        ):
            raise ValueError("Provider lists must contain named endpoints")
    if "seed" in parameters and type(parameters["seed"]) is not int:
        raise ValueError("Seed must be an integer")
    for name, low, high in (
        ("temperature", 0, 2),
        ("top_p", 0, 1),
        ("min_p", 0, 1),
        ("top_a", 0, 1),
        ("frequency_penalty", -2, 2),
        ("presence_penalty", -2, 2),
        ("repetition_penalty", 0, 2),
    ):
        if name in parameters and (
            type(parameters[name]) not in (int, float)
            or not low <= parameters[name] <= high
        ):
            raise ValueError("Sampling parameter outside its supported range")
    if "top_k" in parameters and (
        type(parameters["top_k"]) is not int or parameters["top_k"] < 1
    ):
        raise ValueError("top_k must be a positive integer")
    if parameters.get("top_p") == 0 or parameters.get("repetition_penalty") == 0:
        raise ValueError("top_p and repetition_penalty must be positive")
    if (
        "parallel_tool_calls" in parameters
        and type(parameters["parallel_tool_calls"]) is not bool
    ):
        raise ValueError("parallel_tool_calls must be boolean")
    if "stop" in parameters and not (
        isinstance(parameters["stop"], str)
        or isinstance(parameters["stop"], list)
        and all(isinstance(x, str) for x in parameters["stop"])
    ):
        raise ValueError("Unsupported stop sequence")
    for name in ("reasoning", "response_format"):
        if name in parameters and not isinstance(parameters[name], dict):
            raise ValueError("Structured model parameters must be objects")
    if "tools" in parameters and not isinstance(parameters["tools"], list):
        raise ValueError("Tools must be a list")
    payload = {
        "model": request.request.model_id,
        "messages": messages,
        "stream": False,
        **parameters,
    }
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
