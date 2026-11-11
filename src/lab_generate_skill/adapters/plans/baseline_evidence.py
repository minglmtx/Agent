"""Actual initial-state dependency graph; independent of publication/permissions."""

from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    InitialStateChecks,
    assemble_baseline,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.preparation import (
    EnvironmentBaseline,
    PreparedTask,
    PreparationReceipt,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.state_records import BaselineInputReads
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
    require_baseline_recoveries,
)
from lab_generate_skill.domain.lifecycle import OperationContext


class BaselineEvidenceReader:
    def __init__(
        self, store: EvidenceReader, *, input_reads: BaselineInputReads | None = None
    ) -> None:
        self.reads = StateReads(store)
        self.observations = ObservationReader(store)
        self.input_reads = input_reads

    def verify(
        self,
        receipt: BaselineReceipt,
        control: OperationControl,
        *,
        operation: OperationContext | None = None,
    ) -> BaselineInputs:
        receipt = BaselineReceipt.model_validate(receipt)
        control.checkpoint()
        if self.input_reads is not None and operation is not None:
            request = BaselineReadRequest(receipt=receipt, operation=operation)
            loaded = self.input_reads.load_baseline_inputs(request, control)
            if loaded is not None:
                loaded = BaselineReadBodies.model_validate(loaded)
                if loaded.request != request:
                    raise OwnershipConflict("Baseline proof changed original request")
                control.checkpoint()
                return loaded.inputs
        read = self.reads.parse
        spec = read(receipt.spec_ref, "initial-state-spec/1", InitialStateSpec, control)
        environment = read(
            receipt.environment_ref,
            "environment-baseline/1",
            EnvironmentBaseline,
            control,
        )
        prepared = read(receipt.prepared_ref, "prepared-task/1", PreparedTask, control)
        preparation = read(
            prepared.preparation_ref,
            "preparation-receipt/1",
            PreparationReceipt,
            control,
        )
        initial = read(
            receipt.initial_checks_ref,
            "initial-state-checks/1",
            InitialStateChecks,
            control,
        )
        binding = read(
            prepared.task_binding_ref, "task-binding/1", TaskBinding, control
        )
        public = read(
            binding.public_task_ref,
            "public-task/1",
            PublicTask,
            control,
            visibility="public",
        )
        observation = self.observations.load(receipt.observation_ref, control).record
        inputs = BaselineInputs(
            binding=binding,
            public_task=public,
            spec=spec,
            spec_ref=receipt.spec_ref,
            environment=environment,
            environment_ref=receipt.environment_ref,
            preparation=preparation,
            preparation_ref=prepared.preparation_ref,
            prepared=prepared,
            prepared_ref=receipt.prepared_ref,
            observation=observation,
            observation_ref=receipt.observation_ref,
            initial=initial,
            initial_ref=receipt.initial_checks_ref,
        )
        if assemble_baseline(inputs, receipt.operation) != receipt:
            raise OwnershipConflict(
                "Baseline summary differs from actual initial facts"
            )
        task_recovery = read(
            prepared.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        environment_recovery = read(
            environment.allocation.recovery_ref,
            "recovery-plan/1",
            RecoveryPlan,
            control,
        )
        require_baseline_recoveries(
            inputs, receipt, task_recovery, environment_recovery
        )
        self.reads.dependencies((inputs, task_recovery, environment_recovery), control)
        control.checkpoint()
        return inputs
