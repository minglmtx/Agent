"""One durable invocation through an already acquired real worker.

Only DurableGeneratorInference invokes after first intent commit under its
stable lock. This adapter never acquires a resource or grants a new dispatch.
A returned exchange is persisted even if the resource subsequently closes;
recording failure leaves the durable invocation unresolved, never retried.
"""

from lab_generate_skill.domain.local_generator import (
    LocalGeneratorIntent,
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.ports.generator_executions import GeneratorExecutions
from lab_generate_skill.ports.lifecycle import OperationControl
from .generator_execution_scope import GeneratorExecutionScope
from .generator_execution_capture import record_generator_exchange
from .generator_execution_authority import ResourceGeneratorExecutionAuthority


class ResourceGeneratorInvocation:
    def __init__(
        self, scope: GeneratorExecutionScope, records: GeneratorExecutions
    ) -> None:
        self.scope, self.records = scope, records

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        # Authorize_generate checks live resource before this preflight. Actual
        # invoke rechecks it after the durable intent commit and before sending.
        self.scope.engine.validate(request, parameters, control)

    def invoke(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        intent = LocalGeneratorIntent.model_validate(intent)
        ResourceGeneratorExecutionAuthority(
            self.scope, self.records
        ).authorize_generate(intent, request, parameters, control)
        observed = self.scope.engine.generate_exchange(request, parameters, control)
        record = record_generator_exchange(
            self.scope.evidence,
            self.records,
            self.scope.spec,
            self.scope.acquired_ref,
            intent,
            self.scope.guard,
            observed,
            control,
        )
        return self.records.output(record, control)
