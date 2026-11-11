"""Qwen3 Generator wrapper over shared offline causal-model mechanics."""

from pathlib import Path
from lab_generate_skill.domain.generator_engine import GeneratorEngineConfig
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .causal_transformers import CausalTransformersSession


class TransformersGeneratorSession(CausalTransformersSession):
    def __init__(self, root: Path, config: GeneratorEngineConfig) -> None:
        super().__init__(root, GeneratorEngineConfig.model_validate(config))

    def tokenize(
        self, request: GeneratorModelRequest, parameters: LocalGeneratorParameters
    ) -> tuple[int, ...]:
        return self._tokenize(
            [m.model_dump() for m in request.messages], parameters.enable_thinking
        )

    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        value = self._infer(tokens, parameters, control)
        return LocalGeneratorOutput.model_validate(value.model_dump())
