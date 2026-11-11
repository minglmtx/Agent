"""Bounded canonical local inference evidence; no engine or state transitions."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.generator_model import (
    GeneratorModelRequest,
    GeneratorTextCompletion,
    MAX_GENERATOR_RESPONSE_BYTES,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
    LocalGeneratorIntent,
    LocalGeneratorFact,
    generator_evidence_metadata,
)
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


def local_metadata(schema: str) -> EvidenceMetadata:
    return generator_evidence_metadata(schema)


class LocalGeneratorEvidence:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def read(self, ref: EvidenceRef, limit: int, control: OperationControl) -> bytes:
        if not 0 < ref.size_bytes <= limit:
            raise EvidenceIntegrityError("Local Generator evidence exceeds bound")
        control.checkpoint()
        raw = self._store.read(ref, control=control)
        if (
            type(raw) is not bytes
            or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256
        ):
            raise EvidenceIntegrityError(
                "Local Generator evidence differs from reference"
            )
        control.checkpoint()
        return raw

    def parameters(
        self,
        binding: LocalGeneratorBinding,
        request: GeneratorModelRequest,
        control: OperationControl,
    ) -> LocalGeneratorParameters:
        raw = self.read(
            binding.base_parameters_ref, MAX_GENERATOR_RESPONSE_BYTES, control
        )
        base = LocalGeneratorBaseParameters.model_validate_json(raw)
        if base.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError(
                "Local Generator base parameters are not canonical"
            )
        return LocalGeneratorParameters.model_validate(
            {
                **base.model_dump(),
                "schema_version": "local-generator-parameters/1",
                "seed": request.seed,
                "temperature": request.temperature,
            }
        )

    def put(self, raw: bytes, schema: str, control: OperationControl) -> EvidenceRef:
        expected = evidence_reference(raw, local_metadata(schema))
        control.checkpoint()
        actual = self._store.put(raw, local_metadata(schema), control=control)
        if actual != expected:
            raise EvidenceIntegrityError(
                "Local Generator store changed object identity"
            )
        if self.read(expected, max(len(raw), 1), control) != raw:
            raise EvidenceIntegrityError("Local Generator publication readback differs")
        return actual

    def retain_inputs(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        for raw, schema, expected in (
            (
                request.model_dump_json().encode(),
                "generator-model-request/1",
                intent.request_ref,
            ),
            (
                parameters.model_dump_json().encode(),
                "model-parameters/1",
                intent.parameters_ref,
            ),
        ):
            if self.put(raw, schema, control) != expected:
                raise OwnershipConflict(
                    "Local Generator input differs from original intent"
                )

    def completion(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        ref: EvidenceRef,
        control: OperationControl,
    ) -> GeneratorTextCompletion:
        ref = EvidenceRef.model_validate(ref)
        private_state_ref(ref, "generator-model-response/1")
        raw = self.read(ref, MAX_GENERATOR_RESPONSE_BYTES, control)
        value = GeneratorTextCompletion.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Local Generator completion is not canonical")
        if (
            value.request_id,
            value.generation_input_sha256,
            value.model_input_sha256,
            value.parameters_ref,
        ) != (
            request.request_id,
            request.generation_input_sha256,
            request.model_input_sha256,
            intent.parameters_ref,
        ):
            raise OwnershipConflict(
                "Completion is not for the original local inference"
            )
        return value

    def fact(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        ref: EvidenceRef,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> tuple[LocalGeneratorFact, GeneratorTextCompletion]:
        ref = EvidenceRef.model_validate(ref)
        private_state_ref(ref, "local-generator-fact/1")
        raw = self.read(ref, MAX_GENERATOR_RESPONSE_BYTES + 16384, control)
        fact = LocalGeneratorFact.model_validate_json(raw)
        if fact.model_dump_json().encode() != raw or fact.intent != intent:
            raise OwnershipConflict("Local inference fact differs from original intent")
        completion = self.completion(intent, request, fact.response_ref, control)
        if (fact.output.text, fact.output.finish_reason) != (
            completion.text,
            completion.finish_reason,
        ):
            raise EvidenceIntegrityError("Local output differs from saved completion")
        if (
            fact.output.prompt_tokens > parameters.max_input_tokens
            or fact.output.completion_tokens > parameters.max_new_tokens
        ):
            raise EvidenceIntegrityError("Local engine exceeded frozen token bounds")
        return fact, completion
