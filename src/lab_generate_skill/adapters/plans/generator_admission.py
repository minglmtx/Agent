"""Read actual construction dependencies and re-render the public model input.

No writes, inference, fallback or permission defaults. ConstructionEvidence
reuses original RunPlan/claim/qualified-context checks; the pure projector is
injected without importing a role implementation. Live execution provenance
remains the mandatory LocalGeneratorAuthority's separate responsibility.
"""

import hashlib
from lab_generate_skill.domain.construction import ConstructionCall, ConstructionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.generator_admission import GeneratorRequestProjection
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.observations import Observations
from .construction_evidence import ConstructionEvidence
from .construction_generation import ConstructionGenerationReader


class EvidenceGeneratorCallInputs:
    def __init__(
        self,
        construction: ConstructionEvidence,
        observations: Observations,
        projection: GeneratorRequestProjection,
    ) -> None:
        self._construction, self._observations = construction, observations
        self._projection = projection
        self._generation = ConstructionGenerationReader(
            construction.evidence, construction.retrieval
        )

    def verify(
        self,
        plan: ConstructionPlan,
        call: ConstructionCall,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        plan, call = ConstructionPlan.model_validate(
            plan
        ), ConstructionCall.model_validate(call)
        request = GeneratorModelRequest.model_validate(request)
        parameters = LocalGeneratorParameters.model_validate(parameters)
        op = OperationContext.model_validate(op)
        control.checkpoint()
        self._construction.plan(plan, op, control)
        public = self._generation.load(plan, call, op, control)
        if (
            hashlib.sha256(public.model_dump_json().encode()).hexdigest()
            != call.input_ref.sha256
        ):
            raise OwnershipConflict("Registered Generator input must be canonical")
        observation = self._observations.load(
            public.context.initial_observation_ref, op
        )
        expected = GeneratorModelRequest.model_validate(
            self._projection(public, observation)
        )
        if request != expected:
            raise OwnershipConflict(
                "Actual Generator messages differ from frozen public projection"
            )
        reads = self._construction.reads
        base = reads.parse(
            call.base_parameters_ref,
            "model-parameters/1",
            LocalGeneratorBaseParameters,
            control,
        )
        actual = reads.parse(
            call.parameters_ref, "model-parameters/1", LocalGeneratorParameters, control
        )
        derived = LocalGeneratorParameters.model_validate(
            {
                **base.model_dump(),
                "schema_version": "local-generator-parameters/1",
                "seed": call.seed,
                "temperature": call.temperature,
            }
        )
        if actual != parameters or derived != parameters:
            raise OwnershipConflict(
                "Complete Generator sampling differs from frozen call/base"
            )
        if (
            hashlib.sha256(parameters.model_dump_json().encode()).hexdigest()
            != call.parameters_ref.sha256
        ):
            raise OwnershipConflict("Registered Generator parameters must be canonical")
        control.checkpoint()
