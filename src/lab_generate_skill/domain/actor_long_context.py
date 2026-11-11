"""Explicit Actor-only YaRN recipe and target hardware; no validation grant.

Long profiles remain unpublished until their concrete resource/runtime receipt
is accepted. Both target windows use Qwen's fixed 4x YaRN recipe; a deployment
ceiling of 64K does not imply a guessed factor of two.
"""

from typing import Literal
from pydantic import field_validator
from .validation import Contract


class ActorLongContext(Contract):
    schema_version: Literal["actor-long-context/1"] = "actor-long-context/1"
    gpu_class: Literal["a40", "a100_40gb", "a100_80gb", "rtx_pro_6000_blackwell"]
    rope_type: Literal["yarn"] = "yarn"
    factor: float = 4.0
    original_max_position_embeddings: Literal[32768] = 32768
    attention_backend: Literal["sdpa"] = "sdpa"
    baseline_output_reserve: Literal[4096] = 4096
    min_retained_fraction: float = 0.85

    @property
    def minimum_output_reserve(self) -> int:
        return (self.baseline_output_reserve * 85 + 99) // 100

    @field_validator("min_retained_fraction")
    @classmethod
    def original_output_fraction(cls, value: float) -> float:
        if value != 0.85:
            raise ValueError(
                "Actor output floor is85% of its fixed original4096 reserve"
            )
        return value

    @field_validator("factor")
    @classmethod
    def fixed_official_recipe(cls, value: float) -> float:
        if value != 4.0:
            raise ValueError("The selected Qwen2.5 long recipe requires factor4")
        return value
