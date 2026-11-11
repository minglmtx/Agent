"""Frozen input verification and pure message projection, without execution.

The verifier checks actual plan/context/claim/retrieval and complete parameters.
Projection receives public data only; bootstrap injects the selected version.
Neither operation grants a one-use inference permit or verifies live resources.
"""

from typing import Protocol
from lab_generate_skill.domain.construction import ConstructionCall, ConstructionPlan
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import LocalGeneratorParameters
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.construction_preparation import (
    ConstructionGenerationSource,
)


class GeneratorRequestProjection(Protocol):
    def __call__(
        self, request: GenerationInput, observation: ResolvedObservation
    ) -> GeneratorModelRequest: ...


class GeneratorCallInputs(Protocol):
    def verify(
        self,
        plan: ConstructionPlan,
        call: ConstructionCall,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        op: OperationContext,
        control: OperationControl,
    ) -> None: ...


class ConstructionGeneratorInputs(Protocol):
    def prepare(
        self, plan: ConstructionPlan, op: OperationContext, control: OperationControl
    ) -> ConstructionGenerationSource:
        """Read original public context/top-k and frozen base, never generate."""
        ...


class ConstructionGenerationRecords(Protocol):
    def load(
        self,
        plan: ConstructionPlan,
        call: ConstructionCall,
        op: OperationContext,
        control: OperationControl,
    ) -> GenerationInput:
        """Read original declared public input and qualified top6, no inference."""
        ...
