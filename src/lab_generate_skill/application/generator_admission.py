"""Bind first local inference to actual construction/run state and public input.

This decorates the required execution authority, never replaces live resource,
installed-release or worker provenance checks. It is called inside the durable
inference transaction before validation/intent publication. Revision rechecks
detect changes during admission, not a world lock after return. The execution
authority must enforce exclusive writer ownership through the actual call.
"""

import hashlib
from dataclasses import dataclass
from lab_generate_skill.domain.construction import CallUncertain
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorIntent,
    LocalGeneratorParameters,
    LocalGeneratorFact,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.generator_admission import GeneratorCallInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.local_generator import LocalGeneratorAuthority
from lab_generate_skill.ports.run_journal import RunJournal


@dataclass(frozen=True)
class GeneratorAdmissionDeps:
    construction: ConstructionJournal
    runs: RunJournal
    inputs: GeneratorCallInputs
    execution: LocalGeneratorAuthority


class ConstructionGeneratorAuthority:
    def __init__(self, run: RunBinding, deps: GeneratorAdmissionDeps) -> None:
        self._run, self._deps = RunBinding.model_validate(run), deps

    def _binding(self, binding: LocalGeneratorBinding, op: OperationContext) -> None:
        if (
            binding.owner != self._run.owner
            or binding.release_ref != self._run.release_ref
        ):
            raise OwnershipConflict(
                "Generator does not belong to the original run/release"
            )
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (self._run.owner.run_id, self._run.owner.owner_id, None, None, None):
            raise OwnershipConflict(
                "Generator access requires its original run-level operation"
            )

    def authorize_access(
        self,
        binding: LocalGeneratorBinding,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        binding = LocalGeneratorBinding.model_validate(binding)
        operation = OperationContext.model_validate(operation)
        control.checkpoint()
        self._binding(binding, operation)
        self._deps.execution.authorize_access(binding, operation, control)
        control.checkpoint()

    def authorize_generate(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        intent = LocalGeneratorIntent.model_validate(intent)
        request = GeneratorModelRequest.model_validate(request)
        parameters = LocalGeneratorParameters.model_validate(parameters)
        op = intent.operation
        control.checkpoint()
        self._binding(intent.binding, op)
        construction = ConstructionProgress.model_validate(
            self._deps.construction.read(op)
        )
        snapshot = RunSnapshot.model_validate(self._deps.runs.read(op))
        if construction.plan.run != self._run or snapshot.binding != self._run:
            raise OwnershipConflict("Generator journals belong to another run")
        run, _ = snapshot.project()
        if run.stage != "running" or run.stop_reason is not None:
            raise InvalidTransition(
                "New Generator inference requires an unstopped running run"
            )
        call = construction.project().pending_call
        if call is None or call.role != "generator":
            raise InvalidTransition("No pending Generator call")
        if any(
            isinstance(e, CallUncertain) and e.request_id == call.request_id
            for e in construction.events
        ):
            raise InvalidTransition("Uncertain Generator call cannot start inference")
        model = next(m for m in construction.plan.models if m.role == "generator")
        binding = intent.binding
        if (
            model.paid
            or binding.source_task_id != construction.plan.task.identity.source_task_id
            or (intent.request_id, request.request_id)
            != (call.request_id, call.request_id)
            or (binding.model_binding_ref, call.model_binding_ref)
            != (model.model_binding_ref, model.model_binding_ref)
            or (binding.base_parameters_ref, call.base_parameters_ref)
            != (model.parameters_ref, model.parameters_ref)
            or intent.parameters_ref != call.parameters_ref
            or (
                request.seed,
                request.temperature,
                parameters.seed,
                parameters.temperature,
            )
            != (call.seed, call.temperature, call.seed, call.temperature)
        ):
            raise OwnershipConflict(
                "Generator binding/parameters differ from pending call"
            )
        raw = request.model_dump_json().encode()
        if (intent.request_ref.sha256, intent.request_ref.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise OwnershipConflict(
                "Generator intent does not identify its actual request"
            )
        used = {e.operation.operation_id for e in construction.events}
        used.update(e.event.operation.operation_id for e in snapshot.entries)
        if op.operation_id in used:
            raise OwnershipConflict(
                "Inference cannot reuse a recorded operation identity"
            )
        self._deps.inputs.verify(
            construction.plan, call, request, parameters, op, control
        )
        control.checkpoint()
        self._deps.execution.authorize_generate(intent, request, parameters, control)
        control.checkpoint()
        if (
            ConstructionProgress.model_validate(self._deps.construction.read(op))
            != construction
            or RunSnapshot.model_validate(self._deps.runs.read(op)) != snapshot
        ):
            raise RevisionConflict("Journals changed during Generator admission")
        control.checkpoint()

    def verify_completion(
        self,
        fact: LocalGeneratorFact,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        fact = LocalGeneratorFact.model_validate(fact)
        operation = OperationContext.model_validate(operation)
        control.checkpoint()
        self._binding(fact.intent.binding, operation)
        if operation != fact.intent.operation and not (
            operation.mode == "cleanup"
            and operation.parent_operation_id == fact.intent.operation.operation_id
        ):
            raise OwnershipConflict(
                "Completion must retain the original inference operation"
            )
        self._deps.execution.verify_completion(fact, operation, control)
        control.checkpoint()
