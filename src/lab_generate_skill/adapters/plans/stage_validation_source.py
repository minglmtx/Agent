"""Explicit frozen origin through the existing supervised read consumers.

Old material retains its owner/release. Current caller, parent admission,
storage and durable validation claim are distinct, fresh checks.
"""

from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.source_stage_validation import StageValidationParentChecks
from .closed_source_transport import ClosedSourceReadTransport
from .closed_source_records import (
    SupervisedClosedSourceContexts,
    SupervisedExecutionTaskSourceChecks,
    SupervisedSourceTaskBindingAuthority,
)
from lab_generate_skill.domain.task_publication import TaskBindingInputs
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)


class SupervisedStageValidationContexts(SupervisedClosedSourceContexts):
    def __init__(
        self,
        material: ClosedSourceMaterial,
        transport: ClosedSourceReadTransport,
        controls: OperationControls,
        binding: SourceClaimBinding,
        origin: FrozenExecutionOrigin,
        parent_checks: StageValidationParentChecks,
    ) -> None:
        super().__init__(material, transport, controls)
        if not isinstance(parent_checks, StageValidationParentChecks):
            raise TypeError("Explicit parent admission required")
        self.origin, self.parent_checks = (
            FrozenExecutionOrigin.model_validate(origin),
            parent_checks,
        )
        validation = self.origin.validation
        self.binding = SourceClaimBinding.model_validate(binding)
        validation.require_current_binding(self.binding)

    def require_current(self, op: OperationContext, control: OperationControl) -> None:
        control.checkpoint()
        self.transport.require_stage_validation(
            self.material, self.origin.validation, self.binding, op
        )
        self.transport.check_current(control)
        self.parent_checks.verify_parent(self.origin.validation, op)
        control.checkpoint()

    def load_preparation_inputs(
        self, request: PreparationReadRequest, control: OperationControl
    ) -> PreparationReadBodies:
        request = PreparationReadRequest.model_validate(request)
        self.require_current(request.operation, control)
        self.transport.read(
            self.material,
            control,
            preparation_read=request,
            current_initial_owner=self.binding.run.owner,
        )
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.preparation_bodies is None
            or reply.preparation_bodies.request != request
        ):
            raise OwnershipConflict(
                "Current preparation proof omitted or changed exact inputs"
            )
        self.require_current(request.operation, control)
        return reply.preparation_bodies

    def load_baseline_inputs(
        self, request: BaselineReadRequest, control: OperationControl
    ) -> BaselineReadBodies:
        request = BaselineReadRequest.model_validate(request)
        self.require_current(request.operation, control)
        self.transport.read(
            self.material,
            control,
            baseline_read=request,
            current_initial_owner=self.binding.run.owner,
        )
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.baseline_bodies is None
            or reply.baseline_bodies.request != request
        ):
            raise OwnershipConflict(
                "Current baseline proof omitted or changed exact inputs"
            )
        self.require_current(request.operation, control)
        return reply.baseline_bodies

    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt:
        if reference != self.material.context_ref:
            raise OwnershipConflict("Frozen read cannot select another source context")
        control = self.controls.bind(op)
        self.require_current(op, control)
        result = self.transport.read(self.material, control)
        self.require_current(op, control)
        return result

    def load_context_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        if reference != self.material.context_ref:
            raise OwnershipConflict("Frozen input read changed original context")
        control = self.controls.bind(op)
        self.require_current(op, control)
        result = self.transport.read(self.material, control, context_inputs=True)
        reply = self.transport.last_reply
        if reply is None or reply.context_inputs is None:
            raise OwnershipConflict("Frozen source proof omitted original input bodies")
        self.require_current(op, control)
        return result, reply.context_inputs

    def check_context_current(
        self, op: OperationContext, control: OperationControl
    ) -> None:
        self.require_current(op, control)
        self.transport.check_current(control)
        self.require_current(op, control)


class SupervisedStageValidationSourceChecks(SupervisedExecutionTaskSourceChecks):
    def __init__(
        self,
        owner: OriginalExecutionClaimAuthority,
        contexts: SupervisedStageValidationContexts,
    ) -> None:
        if not isinstance(contexts, SupervisedStageValidationContexts):
            raise TypeError("Explicit frozen-source contexts required")
        super().__init__(owner, contexts.material, contexts.transport)
        if owner.run != contexts.binding.run or owner.task != contexts.binding.task:
            raise OwnershipConflict("Frozen source checks changed current owner/task")
        self.contexts = contexts

    def _current(self, op: OperationContext, control: OperationControl) -> None:
        self.owner.require_caller(op)
        self.contexts.require_current(op, control)

    def _origin(self, facts: ExecutionSourceFacts) -> None:
        if facts.source.frozen_origin != self.contexts.origin:
            raise OwnershipConflict("Source proof changed its selected frozen origin")

    def load_source(
        self, plan: TaskExecutionPlan, op: OperationContext, control: OperationControl
    ) -> ExecutionSourceFacts:
        facts = super().load_source(plan, op, control)
        self._origin(facts)
        self._current(op, control)
        return facts

    def verify_current(
        self,
        plan: TaskExecutionPlan,
        facts: ExecutionSourceFacts,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._origin(facts)
        super().verify_current(plan, facts, op, control)
        self._current(op, control)


class SupervisedStageValidationBindingAuthority(SupervisedSourceTaskBindingAuthority):
    def __init__(
        self,
        owner: OriginalExecutionClaimAuthority,
        contexts: SupervisedStageValidationContexts,
    ) -> None:
        super().__init__(owner, contexts.material, contexts.transport)
        if owner.run != contexts.binding.run or owner.task != contexts.binding.task:
            raise OwnershipConflict("Stage task binding changed current owner/task")
        self.contexts = contexts

    def _current(self, op: OperationContext, control: OperationControl) -> None:
        self.owner.require_caller(op)
        self.contexts.require_current(op, control)

    def load_binding_inputs(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> TaskBindingInputs:
        value = super().load_binding_inputs(reference, op, control)
        self._current(op, control)
        return value

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify_binding(
            binding, public_task, private_spec, baseline, op, control
        )
        self._current(op, control)
