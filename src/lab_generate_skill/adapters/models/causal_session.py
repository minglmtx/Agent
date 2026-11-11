"""Internal structural view of validated role settings; never a wire contract."""

from dataclasses import dataclass
from typing import Protocol
from pydantic import Field
from lab_generate_skill.domain.validation import Contract, NonEmptyText


@dataclass(frozen=True)
class CausalPositionOverride:
    original_window: int
    maximum_window: int
    rope_scaling: dict[str, str | int | float]
    attention_backend: str


class CausalEngineSettings(Protocol):
    @property
    def model_type(self) -> str: ...
    @property
    def dtype(self) -> str: ...
    @property
    def device(self) -> str: ...
    @property
    def cpu_threads(self) -> int: ...
    @property
    def context_window(self) -> int: ...


class CausalSampling(Protocol):
    @property
    def max_new_tokens(self) -> int: ...
    @property
    def seed(self) -> int: ...
    @property
    def temperature(self) -> float: ...
    @property
    def top_p(self) -> float: ...


class CausalOutput(Contract):
    text: str
    finish_reason: NonEmptyText
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
