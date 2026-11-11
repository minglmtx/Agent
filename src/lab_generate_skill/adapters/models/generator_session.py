"""Typed boundary around resident tokenizer/model objects, private to adapters."""

from pathlib import Path
from typing import Protocol
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.generator_engine import GeneratorEngineConfig
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class GeneratorSession(Protocol):
    def tokenize(
        self, request: GeneratorModelRequest, parameters: LocalGeneratorParameters
    ) -> tuple[int, ...]: ...
    def infer(
        self,
        tokens: tuple[int, ...],
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput: ...
    def close(self) -> None: ...


class GeneratorSessionLoader(Protocol):
    def __call__(
        self, root: Path, config: GeneratorEngineConfig
    ) -> GeneratorSession: ...
