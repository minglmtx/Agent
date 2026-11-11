"""Qwen2.5 Actor wrapper; never presents an Actor prompt as a Generator request."""

from pathlib import Path
import importlib
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.ports.lifecycle import OperationControl
from .causal_transformers import CausalTransformersSession
from .actor_long_context import actor_position_override


class TransformersActorSession(CausalTransformersSession):
    def __init__(self, root: Path, config: ActorEngineConfig) -> None:
        config = ActorEngineConfig.model_validate(config)
        position = None
        if config.schema_version == "actor-engine-config/2":
            position = actor_position_override(config, importlib.import_module("torch"))
        super().__init__(root, config, position=position)

    def tokenize(
        self, request: ActorPrompt, parameters: LocalActorParameters
    ) -> tuple[int, ...]:
        return self._tokenize(
            [m.model_dump() for m in request.messages], parameters.enable_thinking
        )

    def tokenize_observation(self, text: str) -> tuple[int, ...]:
        if type(text) is not str or self._model is None or self._tokenizer is None:
            raise ValueError(
                "Original open Actor tokenizer and exact observation text required"
            )
        encoded = self._tokenizer(
            text,
            truncation=False,
            add_special_tokens=False,
            return_attention_mask=False,
        )
        values = encoded["input_ids"]
        if type(values) is not list or any(
            type(value) is not int or value < 0 for value in values
        ):
            raise ValueError(
                "Native observation tokenizer returned invalid token identities"
            )
        return tuple(values)

    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        output = self._infer(tokens, parameters, control)
        return LocalActorOutput.model_validate(output.model_dump())
