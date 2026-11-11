"""Reserve -> commit unique dispatch -> send once -> save -> settle.

No permit is accepted from callers or returned. Concurrent invocations and new
instances/processes must share the same authoritative RequestLedger. A failed
dispatch acknowledgement never reaches transport; all post-dispatch errors
remain unconfirmed with known CAS references. Reconcile cannot call transport.
"""

from lab_generate_skill.adapters.processes.deadline import DeadlineControl

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generation import (
    DispatchPermit,
    RequestRecord,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ModelSendPlan, check_model_cleanup
from lab_generate_skill.domain.model_response import (
    ModelSendFact,
    ModelSendResult,
    ModelSendUnconfirmed,
    ProviderReply,
    ModelTransportFailure,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.model import ModelSendAuthority, ModelTransport
from lab_generate_skill.ports.requests import RequestLedger
from .send_evidence import ModelSendEvidence


class LedgerModelSender:
    def __init__(
        self,
        ledger: RequestLedger,
        transport: ModelTransport,
        evidence: EvidenceStore,
        controls: OperationControls,
        authority: ModelSendAuthority,
    ) -> None:
        self._ledger, self._transport = ledger, transport
        self._evidence = ModelSendEvidence(evidence)
        self._controls, self._authority = controls, authority

    def generate(self, plan: ModelSendPlan) -> ModelSendResult:
        plan = ModelSendPlan.model_validate(plan)
        request, op = plan.reservation.request, plan.operation
        control = self._controls.bind(op)
        control.checkpoint()
        # Detect an already expired cleanup budget before spending any money.
        self._controls.bind(plan.settlement_operation).checkpoint()
        resolved = self._evidence.resolve(plan, control=control)
        control.checkpoint()
        self._transport.validate(resolved, op)
        control.checkpoint()
        self._authority.verify(plan, resolved)
        control.checkpoint()
        reservation = Reservation.model_validate(
            self._ledger.reserve(
                plan.reservation.scope,
                request,
                plan.reservation.ceiling,
                plan.reserve_operation,
            )
        )
        if reservation != plan.reservation:
            raise OwnershipConflict("Ledger returned a different reservation")
        control.checkpoint()
        response_ref: EvidenceRef | None = None
        fact_ref: EvidenceRef | None = None
        stage = "dispatch"
        try:
            permit = DispatchPermit.model_validate(
                self._ledger.mark_dispatching(
                    reservation,
                    expected_revision=0,
                    op=op,
                )
            )
            if (
                permit.request,
                permit.dispatch_operation_id,
                permit.request_revision,
            ) != (request, op.operation_id, 1):
                raise OwnershipConflict("Ledger returned an unrelated dispatch permit")
            control.checkpoint()
            stage = "send"
            reply = ProviderReply.model_validate(self._transport.send(resolved, op))
            # Save a returned fact before checking cancellation/deadline. It is
            # never safe to retry the model to reconstruct a lost response.
            stage = "response"
            # Retain only the already returned bytes under a fresh bounded
            # diagnostic deadline; this grants neither send nor settlement.
            retention = DeadlineControl(5, "model-response-retention")
            response_ref = self._evidence.response(
                plan,
                reply.raw_response,
                control=retention,
            )
            if reply.request_id != request.request_id:
                raise OwnershipConflict("Provider reply belongs to another request")
            if len(reply.raw_response) > plan.limits.max_response_bytes:
                raise ValueError("Transport violated its bounded response contract")
            fact = ModelSendFact(
                request=request,
                operation=op,
                response_ref=response_ref,
                provider_request_id=reply.provider_request_id,
                charge=reply.charge,
            )
            stage = "fact"
            fact_ref = self._evidence.publish(fact, control=retention)
            stage = "settlement"
            return self.reconcile(plan, fact_ref, plan.settlement_operation)
        except BaseException as error:
            if isinstance(error, ModelSendUnconfirmed):
                raise
            raise ModelSendUnconfirmed(
                request.request_id,
                stage,
                response_ref,
                fact_ref,
                error.reference if isinstance(error, ModelTransportFailure) else None,
            ) from error

    def reconcile(
        self, plan: ModelSendPlan, fact_ref: EvidenceRef, op: OperationContext
    ) -> ModelSendResult:
        plan, op = ModelSendPlan.model_validate(plan), OperationContext.model_validate(
            op
        )
        check_model_cleanup(plan.operation, op)
        control = self._controls.bind(op)
        control.checkpoint()
        fact = self._evidence.load(plan, fact_ref, control=control)
        try:
            control.checkpoint()
            record = RequestRecord.model_validate(self._ledger.read(fact.request, op))
            if record.reservation != plan.reservation or not any(
                event.state == "dispatching"
                and event.operation_id == plan.operation.operation_id
                for event in record.events
            ):
                raise OwnershipConflict("Response requires its exact original dispatch")
            receipt = self._ledger.settle(
                fact.request, fact.proof(fact_ref), record.revision, op
            )
            result = ModelSendResult(fact=fact, fact_ref=fact_ref, settlement=receipt)
            control.checkpoint()
            return result
        except BaseException as error:
            raise ModelSendUnconfirmed(
                fact.request.request_id, "settlement", fact.response_ref, fact_ref
            ) from error
