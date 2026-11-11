"""Runtime layer of admission; compose with construction/source business checks.

Completion is checked against durable exact worker exchange and original ledger
acquisition, never an in-memory output cache. Original resource may be closed.
This scope is bound to the original controller; no new-process recovery rights.
"""

import hashlib
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.generator_model import (
    GeneratorModelRequest,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorIntent,
    LocalGeneratorParameters,
    LocalGeneratorFact,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.generator_executions import GeneratorExecutions
from lab_generate_skill.ports.lifecycle import OperationControl
from .generator_execution_scope import GeneratorExecutionScope
from .local_generator_evidence import LocalGeneratorEvidence, local_metadata
from .generator_execution_evidence import read_exact


class ResourceGeneratorExecutionAuthority:
    def __init__(
        self, scope: GeneratorExecutionScope, records: GeneratorExecutions
    ) -> None:
        self.scope, self.records = scope, records

    def authorize_access(
        self,
        binding: LocalGeneratorBinding,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.scope.access(binding, operation, control)

    def authorize_generate(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        intent = LocalGeneratorIntent.model_validate(intent)
        request, parameters = GeneratorModelRequest.model_validate(
            request
        ), LocalGeneratorParameters.model_validate(parameters)
        self.scope.access(intent.binding, intent.operation, control)
        raw = request.model_dump_json().encode()
        if (request.request_id, len(raw), hashlib.sha256(raw).hexdigest()) != (
            intent.request_id,
            intent.request_ref.size_bytes,
            intent.request_ref.sha256,
        ):
            raise OwnershipConflict("Runtime request differs from original intent")
        expected = LocalGeneratorEvidence(self.scope.evidence).parameters(
            intent.binding, request, control
        )
        if (
            parameters != expected
            or evidence_reference(
                parameters.model_dump_json().encode(),
                local_metadata("model-parameters/1"),
            )
            != intent.parameters_ref
        ):
            raise OwnershipConflict("Runtime sampling differs from original intent")
        self.scope.require_original(intent.operation, control, live=True)

    def verify_completion(
        self,
        fact: LocalGeneratorFact,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        fact, operation = LocalGeneratorFact.model_validate(
            fact
        ), OperationContext.model_validate(operation)
        self.scope.access(fact.intent.binding, operation, control)
        if operation != fact.intent.operation and not (
            operation.mode == "cleanup"
            and operation.parent_operation_id == fact.intent.operation.operation_id
        ):
            raise OwnershipConflict(
                "Completion requires original operation or linked cleanup"
            )
        self.scope.require_original(operation, control, live=False)
        recorded = self.records.load(fact.intent, control)
        if (
            recorded.resource,
            recorded.acquired_ref,
            recorded.guard,
            recorded.spec_ref.sha256,
        ) != (
            self.scope.spec.token,
            self.scope.acquired_ref,
            self.scope.guard,
            hashlib.sha256(self.scope.spec.model_dump_json().encode()).hexdigest(),
        ):
            raise EvidenceIntegrityError(
                "Completion refers to another acquired resource"
            )
        output = self.records.output(recorded, control)
        request = GeneratorModelRequest.model_validate_json(
            read_exact(
                self.scope.evidence, fact.intent.request_ref, 16 * 1024 * 1024, control
            )
        )
        response = GeneratorTextCompletion(
            request_id=request.request_id,
            generation_input_sha256=request.generation_input_sha256,
            model_input_sha256=request.model_input_sha256,
            parameters_ref=fact.intent.parameters_ref,
            text=output.text,
            finish_reason=output.finish_reason,
        )
        if (
            output != fact.output
            or evidence_reference(
                response.model_dump_json().encode(),
                local_metadata("generator-model-response/1"),
            )
            != fact.response_ref
        ):
            raise EvidenceIntegrityError(
                "Completion output differs from recorded original reply"
            )
        control.checkpoint()
