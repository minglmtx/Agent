"""Typed internal boundary around a resident Qwen2.5 Actor session."""

from pathlib import Path
from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.ports.lifecycle import OperationControl


class ActorSession(Protocol):
    def tokenize(
        self, request: ActorPrompt, parameters: LocalActorParameters
    ) -> tuple[int, ...]: ...
    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput: ...
    def close(self) -> None: ...


class ActorSessionLoader(Protocol):
    def __call__(self, root: Path, config: ActorEngineConfig) -> ActorSession: ...


@runtime_checkable
class ActorObservationTokenizer(Protocol):
    def tokenize_observation(self, text: str) -> tuple[int, ...]:
        """Exact body text on the same resident tokenizer, without special tokens."""
        ...
