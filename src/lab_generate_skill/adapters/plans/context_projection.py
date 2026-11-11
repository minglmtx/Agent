"""Bounded strict context metadata decoding, using the existing wire JSON guard."""

from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.context_budget import ContextBudgetProfile
from lab_generate_skill.domain.context_projection import (
    ContextProjectionPolicy,
    ContextSelection,
    ContextDecision,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

T = TypeVar("T", bound=Contract)
MAX_CONTEXT_METADATA = 256 * 1024


def _decode(raw: bytes, model: type[T]) -> T:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CONTEXT_METADATA:
        raise ValueError("Exact bounded context metadata bytes required")
    value = json_object(raw)
    if value.get("schema_version") != model.model_fields["schema_version"].default:
        raise ValueError("Explicit supported context metadata schema required")
    return model.model_validate_json(raw)


def decode_context_budget(raw: bytes) -> ContextBudgetProfile:
    return _decode(raw, ContextBudgetProfile)


def decode_context_policy(raw: bytes) -> ContextProjectionPolicy:
    return _decode(raw, ContextProjectionPolicy)


def decode_context_selection(raw: bytes) -> ContextSelection:
    return _decode(raw, ContextSelection)


def decode_context_decision(raw: bytes) -> ContextDecision:
    return _decode(raw, ContextDecision)
