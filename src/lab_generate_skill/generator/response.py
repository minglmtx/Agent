"""Parse one saved skill response; never repair, truncate or resample it.

Preserve legacy first-JSON-object extraction (including fences/thinking text),
then require exactly the three public skill fields and existing hard limits.
Duplicate JSON keys/nonfinite constants are rejected, not silently collapsed.
"""

import json
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.generator_model import MAX_GENERATOR_RESPONSE_BYTES


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate response JSON field")
        value[key] = item
    return value


def _constant(value: str) -> object:
    raise ValueError("Nonfinite response JSON value")


def parameter_object(raw: bytes) -> dict[str, object]:
    """Strict parameter JSON used to compare actual seed/temperature evidence."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_GENERATOR_RESPONSE_BYTES:
        raise ValueError("Generator parameter bytes outside budget")
    value: object = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("Generator parameters must be an object")
    return value


def parse_generated_skill(text: str, finish_reason: str) -> CompactSkill:
    if type(text) is not str or type(finish_reason) is not str:
        raise TypeError("Generator text and finish reason must be strings")
    if finish_reason != "stop":
        raise ValueError("Generator did not finish normally; retain original response")
    if not text.strip() or len(text.encode()) > MAX_GENERATOR_RESPONSE_BYTES:
        raise ValueError("Generator response is empty or exceeds byte budget")
    decoder = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=_constant)
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            if set(value) != {"title", "principle", "when_to_apply"}:
                raise ValueError("Generator must return exactly three skill fields")
            return CompactSkill.model_validate(value)
    raise ValueError("No valid skill JSON object in Generator response")
