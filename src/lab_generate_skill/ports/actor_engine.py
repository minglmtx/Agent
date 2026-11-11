"""Worker-local Actor engine; external process supervisor and live authority required."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.actor_engine import (
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_context_count import ActorTokenCount
from .lifecycle import OperationControl


class LocalActorEngine(Protocol):
    def measure(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> ActorTokenCount: ...
    def validate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> None: ...
    def generate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput: ...
    def close(self, control: OperationControl) -> None: ...


@runtime_checkable
class PreparedActorEngine(Protocol):
    """Consume the exact, single pending validation without loading/counting again."""

    def generate_prepared(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput: ...
