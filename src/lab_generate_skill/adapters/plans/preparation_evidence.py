"""Load original persisted preparation graph; never synthesize missing history."""

from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationInputs,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.task_bindings import TaskBindings, TaskBindingInputLoads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_record_inputs import (
    LoadedPreparation as LoadedPreparation,
)
from .state_reads import StateReads


class PreparationEvidenceReader:
    def __init__(self, store: EvidenceReader, bindings: TaskBindings) -> None:
        self.reads, self.bindings = StateReads(store), bindings

    def load(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
    ) -> PreparationInputs:
        return self.load_with_bodies(selection, op, control).inputs

    def load_with_bodies(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
    ) -> LoadedPreparation:
        selection = PreparationSelection.model_validate(selection)
        read = self.reads.parse
        request = read(
            selection.request_ref, "site-task-request/2", SiteTaskRequest, control
        )
        result = read(
            selection.result_ref, "site-task-result/1", SiteTaskResult, control
        )
        # These bodies remain local to this call. Every subsequent load reads
        # again and rechecks original permission; nothing is a cached grant.
        verified: set[EvidenceRef] = {selection.request_ref, selection.result_ref}
        private_body: bytes | None = None
        snapshot_body: bytes | None = None
        if (
            isinstance(self.bindings, TaskBindingInputLoads)
            and self.bindings.loads_inputs_in_one_call
        ):
            facts = self.bindings.load_inputs(request.binding_ref, op)
            binding, public = TaskBinding.model_validate(
                facts.binding
            ), PublicTask.model_validate(facts.public_task)
            private_state_ref(binding.baseline_ref, "initial-state-spec/1")
            if public.identity != binding.identity:
                raise OwnershipConflict(
                    "Binding input bodies changed original public task"
                )
            require_complete_bytes(binding.private_spec_ref, facts.private_spec)
            private_body = facts.private_spec
            require_complete_bytes(binding.baseline_ref, facts.baseline)
            spec = InitialStateSpec.model_validate_json(facts.baseline)
            verified.update(
                (
                    request.binding_ref,
                    binding.public_task_ref,
                    binding.private_spec_ref,
                    binding.baseline_ref,
                )
            )
        else:
            binding = self.bindings.load(request.binding_ref, op)
            public = read(
                binding.public_task_ref,
                "public-task/1",
                PublicTask,
                control,
                visibility="public",
            )
            spec = read(
                binding.baseline_ref, "initial-state-spec/1", InitialStateSpec, control
            )
            verified.update((binding.public_task_ref, binding.baseline_ref))
        environment = read(
            selection.environment_ref,
            "environment-baseline/1",
            EnvironmentBaseline,
            control,
        )
        assert request.operation.recovery_ref is not None
        recovery = read(
            request.operation.recovery_ref, "recovery-plan/1", RecoveryPlan, control
        )
        inputs = PreparationInputs(
            selection=selection,
            request=request,
            result=result,
            binding=binding,
            public_task=public,
            spec=spec,
            environment=environment,
            recovery=recovery,
        )
        verified.update((selection.environment_ref, request.operation.recovery_ref))
        # Preserve transitive dependency checks. The exact bodies physically
        # read earlier in this same call need no second storage exchange.
        for reference in dict.fromkeys(evidence_references(inputs)):
            control.checkpoint()
            if reference not in verified:
                raw = self.reads.read(reference, control)
                if reference == binding.private_spec_ref:
                    require_complete_bytes(reference, raw)
                    private_body = raw
                if reference == request.snapshot_ref:
                    require_complete_bytes(reference, raw)
                    snapshot_body = raw
                verified.add(reference)
        control.checkpoint()
        return LoadedPreparation(
            inputs, frozenset(verified), private_body, snapshot_body
        )
