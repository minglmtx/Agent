"""Same-owner production readonly records; all live caller checks remain fresh."""

from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedSourceMaterial,
    ClosedSourceBindingInput,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
)
from lab_generate_skill.domain.initial_equivalence import EquivalenceReceipt
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.task_publication import TaskBindingInputs
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.contexts import ContextRecords, ContextFactReads
from .closed_source_transport import ClosedSourceReadTransport
from pydantic import TypeAdapter
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.ports.preparation_records import PreparationInputReads
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.ports.state_records import BaselineInputReads


class ClosedSourceContexts:
    """Read exactly the frozen source, without mutating any source record."""

    def __init__(self, records: ContextRecords, reference: EvidenceRef) -> None:
        self._records, self._reference = records, reference

    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt:
        if reference != self._reference:
            raise OwnershipConflict(
                "Closed source reader cannot select a different source"
            )
        return self._records.load_context(reference, op)

    def load_context_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        if reference != self._reference:
            raise OwnershipConflict("Closed source inputs changed original reference")
        # All fixed source readers wrap the original EvidenceContextRecords or
        # supervised adapter. No alternative graph verifier is introduced.
        from lab_generate_skill.adapters.storage.context_records import (
            EvidenceContextRecords,
        )

        if isinstance(self._records, EvidenceContextRecords):
            return self._records.load_context_inputs(reference, op)
        if isinstance(self._records, ContextFactReads):
            return self._records.load_context_inputs(reference, op)
        raise TypeError("Original complete context input reader required")

    def check_context_current(
        self, op: OperationContext, control: OperationControl
    ) -> None:
        if isinstance(self._records, ContextFactReads):
            self._records.check_context_current(op, control)
        else:
            # Legacy local readers keep their complete current authority path.
            self._records.load_context(self._reference, op)
        control.checkpoint()

    def load_preparation_inputs(
        self, request: PreparationReadRequest, control: OperationControl
    ) -> PreparationReadBodies | None:
        if isinstance(self._records, PreparationInputReads):
            return self._records.load_preparation_inputs(request, control)
        return None

    def load_baseline_inputs(
        self,
        request: BaselineReadRequest,
        control: OperationControl,
    ) -> BaselineReadBodies | None:
        if isinstance(self._records, BaselineInputReads):
            return self._records.load_baseline_inputs(request, control)
        return None

    def publish_context(self, *args: object, **kwargs: object) -> EvidenceRef:
        raise PermissionError("Closed source reader cannot publish")

    def publish_equivalence(self, *args: object, **kwargs: object) -> EvidenceRef:
        raise PermissionError(
            "Closed source reader cannot publish candidate equivalence"
        )

    def load_equivalence(self, *args: object, **kwargs: object) -> EquivalenceReceipt:
        raise PermissionError(
            "Closed source reader cannot qualify candidate equivalence"
        )


class SupervisedClosedSourceContexts:
    def __init__(
        self,
        material: ClosedSourceMaterial,
        transport: ClosedSourceReadTransport,
        controls: OperationControls,
    ) -> None:
        self.material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        if not isinstance(transport, ClosedSourceReadTransport) or controls is None:
            raise TypeError("Original controlled source read and controls required")
        self.transport, self.controls = transport, controls

    def load_preparation_inputs(
        self, request: PreparationReadRequest, control: OperationControl
    ) -> PreparationReadBodies:
        request = PreparationReadRequest.model_validate(request)
        self.transport.require_current(self.material, request.operation)
        self.transport.read(self.material, control, preparation_read=request)
        reply = self.transport.last_reply
        if reply is None or reply.preparation_bodies is None:
            raise OwnershipConflict("Original preparation input proof was omitted")
        if reply.preparation_bodies.request != request:
            raise OwnershipConflict("Original preparation input selection changed")
        return reply.preparation_bodies

    def load_baseline_inputs(
        self,
        request: BaselineReadRequest,
        control: OperationControl,
    ) -> BaselineReadBodies:
        request = BaselineReadRequest.model_validate(request)
        self.transport.require_current(self.material, request.operation)
        self.transport.read(self.material, control, baseline_read=request)
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.baseline_bodies is None
            or reply.baseline_bodies.request != request
        ):
            raise OwnershipConflict(
                "Original baseline input proof was omitted or changed"
            )
        self.transport.require_current(self.material, request.operation)
        control.checkpoint()
        return reply.baseline_bodies

    def load_context(
        self, reference: EvidenceRef, op: OperationContext
    ) -> PublicContextReceipt:
        if reference != self.material.context_ref:
            raise OwnershipConflict("Readonly source cannot select a different context")
        self.transport.require_current(self.material, op)
        return self.transport.read(self.material, self.controls.bind(op))

    def load_context_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> tuple[PublicContextReceipt, PublicContextInputs]:
        if reference != self.material.context_ref:
            raise OwnershipConflict("Context input read changed original reference")
        self.transport.require_current(self.material, op)
        context = self.transport.read(
            self.material, self.controls.bind(op), context_inputs=True
        )
        reply = self.transport.last_reply
        if reply is None or reply.context_inputs is None:
            raise OwnershipConflict(
                "Whole source proof omitted complete context inputs"
            )
        return context, reply.context_inputs

    def check_context_current(
        self, op: OperationContext, control: OperationControl
    ) -> None:
        self.transport.require_current(self.material, op)
        self.transport.check_current(control)

    def publish_context(self, *args: object, **kwargs: object) -> EvidenceRef:
        raise PermissionError("Closed source reader cannot publish")

    def publish_equivalence(self, *args: object, **kwargs: object) -> EvidenceRef:
        raise PermissionError("Closed source reader cannot compare a candidate")

    def load_equivalence(self, *args: object, **kwargs: object) -> EquivalenceReceipt:
        raise PermissionError(
            "Closed source reader cannot qualify candidate equivalence"
        )


class SupervisedSourceTaskBindingAuthority:
    def __init__(
        self,
        owner: OriginalExecutionClaimAuthority,
        material: ClosedSourceMaterial,
        transport: ClosedSourceReadTransport,
    ) -> None:
        if not isinstance(owner, OriginalExecutionClaimAuthority) or not isinstance(
            transport, ClosedSourceReadTransport
        ):
            raise TypeError(
                "Original current claim owner and controlled source reader required"
            )
        self.owner, self.material, self.transport = (
            owner,
            TypeAdapter[ClosedSourceMaterial](ClosedSourceMaterial).validate_python(
                material, strict=True
            ),
            transport,
        )

    def _current(self, op: OperationContext, control: OperationControl) -> None:
        self.owner.require_caller(op)
        self.transport.require_current(self.material, op)
        control.checkpoint()

    def load_binding(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> TaskBinding:
        return self.load_binding_inputs(reference, op, control).binding

    def load_binding_inputs(
        self, reference: EvidenceRef, op: OperationContext, control: OperationControl
    ) -> TaskBindingInputs:
        # Same fixed worker verifies the reference, all dependency bytes and the
        # original qualified-binding algorithm. Dynamic rights remain here.
        self._current(op, control)
        self.transport.read(self.material, control, binding_reference=reference)
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.binding_reference != reference
            or reply.binding != self.owner.task
            or reply.binding_bodies is None
        ):
            raise OwnershipConflict(
                "Task-reference proof changed original task/reference"
            )
        self.owner.require_caller(op)
        control.checkpoint()
        return reply.binding_bodies.inputs()

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._current(op, control)
        if binding != self.owner.task:
            raise OwnershipConflict("Binding changed original source task definition")
        selected = ClosedSourceBindingInput(
            binding=binding,
            public_task=public_task,
            private_spec_json=private_spec.decode(),
            baseline_json=baseline.decode(),
        )
        self.transport.read(self.material, control, binding=selected)
        self.owner.require_caller(op)
        control.checkpoint()


class SupervisedRunPlanInputChecks:
    """Same fixed whole-graph worker; every invocation rechecks all input bytes.

    This replaces leaf RPCs, never caller/claim/once/resource checks. It holds
    the original store lock, current admission, owner and installed-source proof.
    """

    def __init__(
        self, material: ClosedSourceMaterial, transport: ClosedSourceReadTransport
    ) -> None:
        self.material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        if not isinstance(transport, ClosedSourceReadTransport):
            raise TypeError("Original installed controlled reader required")
        self.transport = transport

    def verify_inputs(
        self, plan: RunPlan, op: OperationContext, control: OperationControl
    ) -> None:
        plan = RunPlan.model_validate(plan)
        if plan.run_id != self.material.site.token.owner.run_id:
            raise OwnershipConflict("Plan inputs changed the original source owner")
        # Current controller/release and storage admission are checked anew.
        # The parent caller's operation remains the controlling deadline.
        self.transport.require_current(self.material, op)
        self.transport.read(self.material, control, plan_inputs=plan)


class SupervisedExecutionTaskSourceChecks:
    """One proof per source load; no live authority or cross-call body cache."""

    def __init__(
        self,
        owner: OriginalExecutionClaimAuthority,
        material: ClosedSourceMaterial,
        transport: ClosedSourceReadTransport,
    ) -> None:
        if not isinstance(owner, OriginalExecutionClaimAuthority) or not isinstance(
            transport, ClosedSourceReadTransport
        ):
            raise TypeError("Original current owner and fixed source reader required")
        self.owner, self.transport = owner, transport
        self.material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)

    def _current(self, op: OperationContext, control: OperationControl) -> None:
        self.owner.require_caller(op)
        self.transport.require_current(self.material, op)
        control.checkpoint()

    def require_current(self, op: OperationContext, control: OperationControl) -> None:
        """Check the selected live source/namespace without changing its origin."""
        self._current(op, control)

    def load_source(
        self, plan: TaskExecutionPlan, op: OperationContext, control: OperationControl
    ) -> ExecutionSourceFacts:
        plan = TaskExecutionPlan.model_validate(plan)
        self._current(op, control)
        if (
            plan.intent.binding.run != self.owner.run
            or plan.intent.binding.task != self.owner.task.identity
        ):
            raise OwnershipConflict(
                "Execution source changed actual original owner/task"
            )
        self.transport.read(self.material, control, execution_plan=plan)
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.execution_source is None
            or reply.execution_claim is None
        ):
            raise OwnershipConflict(
                "Execution source proof omitted original full facts"
            )
        facts = reply.execution_source
        if facts.source.task != self.owner.task or facts.source.run != self.owner.run:
            raise OwnershipConflict(
                "Execution source proof changed full original binding"
            )
        self.owner.require_caller(op)
        control.checkpoint()
        from lab_generate_skill.domain.execution_task_source import (
            ClaimedExecutionSourceFacts,
        )

        return ClaimedExecutionSourceFacts(
            source=facts.source,
            inputs=facts.inputs,
            run=facts.run,
            policy=facts.policy,
            context=facts.context,
            claim=reply.execution_claim,
        )

    def verify_current(
        self,
        plan: TaskExecutionPlan,
        facts: ExecutionSourceFacts,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        """Current owner/store only; immutable facts came from this admission."""
        self._current(op, control)
        if (
            plan.intent.binding.run != self.owner.run
            or plan.intent.binding.task != self.owner.task.identity
            or facts.source.run != self.owner.run
            or facts.source.task != self.owner.task
            or facts.source.intent != plan.intent
            or facts.source.source_context_receipt_ref != self.material.context_ref
        ):
            raise OwnershipConflict("Source handoff changed original owner/task")
        self.transport.check_current(control)
        self.owner.require_caller(op)
        control.checkpoint()
