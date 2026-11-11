"""Generator role through public observation, injected inference and saved facts.

No website/private task binding, paid reservation or runtime handle is accepted.
Exactly one backend invocation per call; persistent ownership/idempotency is the
required inference port's responsibility, never an in-memory role cache.
"""

import hashlib
from lab_generate_skill.domain.construction_inputs import (
    GenerationInput,
    GeneratedCandidate,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generator_model import (
    GeneratorTextCompletion,
    MAX_GENERATOR_RESPONSE_BYTES,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.generator_model import GeneratorInference
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.observations import Observations
from .prompting import prepare_generator
from .response import parse_generated_skill, parameter_object


class RecordedGenerator:
    def __init__(
        self,
        observations: Observations,
        inference: GeneratorInference,
        evidence: EvidenceReader,
        controls: OperationControls,
    ) -> None:
        self._observations, self._inference = observations, inference
        self._evidence, self._controls = evidence, controls

    def _read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        if not 0 < ref.size_bytes <= MAX_GENERATOR_RESPONSE_BYTES:
            raise EvidenceIntegrityError("Generator evidence outside byte budget")
        control.checkpoint()
        raw = self._evidence.read(ref, control=control)
        if (
            type(raw) is not bytes
            or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256
        ):
            raise EvidenceIntegrityError(
                "Generator evidence differs from frozen reference"
            )
        control.checkpoint()
        return raw

    def generate(
        self, request: GenerationInput, op: OperationContext
    ) -> GeneratedCandidate:
        request, op = GenerationInput.model_validate(
            request
        ), OperationContext.model_validate(op)
        if op.mode != "execute" or op.attempt_id is not None:
            raise OwnershipConflict(
                "Generator requires its construction-level execute operation"
            )
        control = self._controls.bind(op)
        control.checkpoint()
        observation = self._observations.load(
            request.context.initial_observation_ref, op
        )
        model_request = prepare_generator(request, observation)
        control.checkpoint()
        response_ref: EvidenceRef | None = None
        try:
            response_ref = EvidenceRef.model_validate(
                self._inference.generate(model_request, op)
            )
            private_state_ref(response_ref, "generator-model-response/1")
            raw = self._read(response_ref, control)
            completion = GeneratorTextCompletion.model_validate_json(raw)
            if completion.model_dump_json().encode() != raw:
                raise EvidenceIntegrityError("Generator completion is not canonical")
            if (
                completion.request_id,
                completion.generation_input_sha256,
                completion.model_input_sha256,
            ) != (
                request.request_id,
                model_request.generation_input_sha256,
                model_request.model_input_sha256,
            ):
                raise OwnershipConflict("Generator completion belongs to another input")
            parameters = parameter_object(
                self._read(completion.parameters_ref, control)
            )
            if (
                type(parameters.get("seed")) is not int
                or parameters["seed"] != request.seed
                or type(parameters.get("temperature")) not in (int, float)
                or parameters["temperature"] != request.temperature
            ):
                raise OwnershipConflict(
                    "Actual Generator sampling differs from the frozen request"
                )
            skill = parse_generated_skill(completion.text, completion.finish_reason)
            result = GeneratedCandidate(
                request_id=request.request_id,
                input_sha256=model_request.generation_input_sha256,
                parameters_sha256=completion.parameters_ref.sha256,
                skill=skill,
                response_ref=response_ref,
            )
            control.checkpoint()
            return result
        except BaseException as error:
            if response_ref is not None:
                error.generator_response_ref = response_ref  # type: ignore[attr-defined]
            raise
