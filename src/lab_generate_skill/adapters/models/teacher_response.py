"""Pure original OpenRouter structured skill and optional usage extraction."""

from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.teacher_revision import TeacherCompletion
from lab_generate_skill.adapters.processes.wire_json import json_object
from .provider_charge import exact_charge


def _tokens(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 2147483647:
        raise ValueError("Actual nonnegative provider token count required")
    return value


class OpenRouterTeacherDecoder:
    def decode(self, raw: bytes) -> TeacherCompletion:
        value = json_object(raw, exact_numbers=True)
        choices = value.get("choices")
        if (
            "error" in value
            or type(value.get("id")) is not str
            or not value["id"].strip()
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise ValueError(
                "One complete original OpenRouter Teacher response required"
            )
        choice = choices[0]
        message = choice.get("message")
        if (
            choice.get("finish_reason") != "stop"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or type(message.get("content")) is not str
            or message.get("tool_calls")
        ):
            raise ValueError(
                "Teacher skill must be one complete stopped structured response"
            )
        payload = json_object(message["content"].encode())
        if set(payload) != {"title", "principle", "when_to_apply"}:
            raise ValueError("Exact original three-field skill response required")
        skill = CompactSkill.model_validate_json(message["content"])
        usage = value.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("Malformed provider usage is not missing usage")
        usage = usage or {}
        details = usage.get("completion_tokens_details")
        if details is not None and not isinstance(details, dict):
            raise ValueError("Malformed reasoning usage")
        details = details or {}
        return TeacherCompletion(
            provider_request_id=value["id"],
            skill=skill,
            charge=exact_charge(usage.get("cost")),
            input_tokens=_tokens(usage.get("prompt_tokens")),
            output_tokens=_tokens(usage.get("completion_tokens")),
            reasoning_tokens=_tokens(details.get("reasoning_tokens")),
        )
