"""Pure composition of one authoritative initial observation and state facts.

The application must load all supplied references and validate their actual
contents before calling assemble_baseline. Metadata consistency is not authority.
"""

from typing import Literal, Self
from pydantic import model_validator
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .lifecycle import OperationContext
from .observation import Observation
from .preparation import EnvironmentBaseline, PreparationReceipt, PreparedTask
from .state_checks import InitialStateSpec, StateChecks
from .state_scope import StateFact, private_state_ref
from .task import TaskBinding, PublicTask
from .validation import Contract, Identifier, Sha256


class InitialStateChecks(StateFact):
    schema_version: Literal["initial-state-checks/1"] = "initial-state-checks/1"
    spec_ref: EvidenceRef
    prepared_ref: EvidenceRef
    observation_ref: EvidenceRef
    checks: StateChecks
    measured_state_sha256: Sha256

    @model_validator(mode="after")
    def references(self) -> Self:
        private_state_ref(self.spec_ref, "initial-state-spec/1")
        private_state_ref(self.prepared_ref, "prepared-task/1")
        if (
            self.observation_ref.visibility != "public"
            or self.observation_ref.content_schema != "observation/1"
        ):
            raise ValueError("Initial checks need the actual public observation")
        return self


class BaselineReceipt(StateFact):
    schema_version: Literal["baseline-receipt/1"] = "baseline-receipt/1"
    spec_ref: EvidenceRef
    environment_ref: EvidenceRef
    prepared_ref: EvidenceRef
    initial_checks_ref: EvidenceRef
    observation_ref: EvidenceRef
    measured_state_sha256: Sha256
    equivalence_scope: tuple[Identifier, ...]
    status: Literal["ready", "rejected", "unknown"]

    @model_validator(mode="after")
    def references(self) -> Self:
        for ref, schema in (
            (self.spec_ref, "initial-state-spec/1"),
            (self.environment_ref, "environment-baseline/1"),
            (self.prepared_ref, "prepared-task/1"),
            (self.initial_checks_ref, "initial-state-checks/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.observation_ref.visibility != "public"
            or self.observation_ref.content_schema != "observation/1"
        ):
            raise ValueError("Baseline observation must remain public")
        if not self.equivalence_scope or len(set(self.equivalence_scope)) != len(
            self.equivalence_scope
        ):
            raise ValueError("Baseline must declare distinct equivalence checks")
        return self


class BaselineInputs(Contract):
    binding: TaskBinding
    public_task: PublicTask
    spec: InitialStateSpec
    spec_ref: EvidenceRef
    environment: EnvironmentBaseline
    environment_ref: EvidenceRef
    preparation: PreparationReceipt
    preparation_ref: EvidenceRef
    prepared: PreparedTask
    prepared_ref: EvidenceRef
    observation: Observation
    observation_ref: EvidenceRef
    initial: InitialStateChecks
    initial_ref: EvidenceRef


def assemble_baseline(
    inputs: BaselineInputs, operation: OperationContext
) -> BaselineReceipt:
    inputs = BaselineInputs.model_validate(inputs)
    operation = OperationContext.model_validate(operation)
    scope = inputs.prepared.scope
    env, prep, initial = inputs.environment, inputs.preparation, inputs.initial
    if (
        inputs.binding.identity,
        inputs.binding.baseline_ref,
        inputs.binding.private_spec_ref,
        inputs.public_task,
    ) != (
        scope.task,
        inputs.spec_ref,
        inputs.prepared.private_checks_ref,
        inputs.prepared.public_task,
    ):
        raise OwnershipConflict(
            "Baseline preparation must preserve actual task binding and public task"
        )
    if (
        len(
            {
                op.operation_id
                for op in (env.operation, prep.operation, initial.operation, operation)
            }
        )
        != 4
    ):
        raise OwnershipConflict("Baseline stages require distinct operation identities")
    if (
        any(value.scope != scope for value in (env, prep, initial))
        or inputs.spec.task != scope.task
    ):
        raise OwnershipConflict(
            "Baseline inputs belong to different task/owner/attempt/context"
        )
    if any(
        ref != inputs.spec_ref
        for ref in (
            env.spec_ref,
            prep.spec_ref,
            inputs.prepared.spec_ref,
            initial.spec_ref,
        )
    ):
        raise OwnershipConflict("Baseline inputs must share frozen state specification")
    if (
        prep.environment_ref,
        inputs.prepared.preparation_ref,
        initial.prepared_ref,
        initial.observation_ref,
    ) != (
        inputs.environment_ref,
        inputs.preparation_ref,
        inputs.prepared_ref,
        inputs.observation_ref,
    ):
        raise OwnershipConflict(
            "Baseline dependencies must follow environment -> prepare -> observation checks"
        )
    if (prep.task_binding_ref, prep.recovery_ref) != (
        inputs.prepared.task_binding_ref,
        inputs.prepared.recovery_ref,
    ):
        raise OwnershipConflict("Preparation differs from prepared binding or recovery")
    observed = inputs.observation
    if (observed.task, observed.context_id, observed.attempt_id, observed.sequence) != (
        scope.task,
        scope.context_id,
        scope.attempt_id,
        0,
    ):
        raise OwnershipConflict(
            "Baseline requires the authoritative initial observation"
        )
    for facts, required in (
        (env.checks, inputs.spec.environment_checks),
        (prep.checks, inputs.spec.preparation_checks),
        (initial.checks, inputs.spec.initial_checks),
    ):
        if facts.required != required:
            raise OwnershipConflict("Baseline cannot narrow frozen required checks")
    statuses = (env.checks.status, prep.checks.status, initial.checks.status)
    status: Literal["ready", "rejected", "unknown"] = "ready"
    if "unknown" in statuses or observed.state != "ready" or observed.last_action_error:
        status = "unknown"
    elif "fail" in statuses:
        status = "rejected"
    return BaselineReceipt(
        scope=scope,
        operation=operation,
        spec_ref=inputs.spec_ref,
        environment_ref=inputs.environment_ref,
        prepared_ref=inputs.prepared_ref,
        initial_checks_ref=inputs.initial_ref,
        observation_ref=inputs.observation_ref,
        measured_state_sha256=initial.measured_state_sha256,
        equivalence_scope=inputs.spec.equivalence_checks,
        status=status,
    )
