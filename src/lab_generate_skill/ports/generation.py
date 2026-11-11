"""Generator receives only the public input view; no implicit retry."""

from typing import Protocol

from lab_generate_skill.domain.construction_inputs import (
    GeneratedCandidate,
    GenerationInput,
)
from lab_generate_skill.domain.lifecycle import OperationContext


class Generator(Protocol):
    def generate(
        self, request: GenerationInput, op: OperationContext
    ) -> GeneratedCandidate: ...
