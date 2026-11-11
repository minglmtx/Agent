"""Original error response -> retained fact -> charged-failure settlement.

No transport dependency, retry or automatic budget release. Shared dispatch
state fences all senders until the existing ledger verifies/commits this proof.
Uncertain/missing facts keep the original fence and reservation intact.
"""

from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generation import RequestRecord
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ModelSendPlan, check_model_cleanup
from lab_generate_skill.domain.model_failure import (
    ModelFailureFact,
    FailureBillingResult,
    FailureBillingPending,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.requests import RequestLedger
from .failure_evidence import FailureEvidence


class LedgerFailureBilling:
    def __init__(
        self,
        ledger: RequestLedger,
        evidence: EvidenceStore,
        controls: OperationControls,
    ) -> None:
        self._ledger, self._evidence, self._controls = (
            ledger,
            FailureEvidence(evidence),
            controls,
        )

    def reconcile(
        self, plan: ModelSendPlan, transport_ref: EvidenceRef, op: OperationContext
    ) -> FailureBillingResult:
        plan, op = ModelSendPlan.model_validate(plan), OperationContext.model_validate(
            op
        )
        check_model_cleanup(plan.operation, op)
        control = self._controls.bind(op)
        control.checkpoint()
        record = RequestRecord.model_validate(
            self._ledger.read(plan.reservation.request, op)
        )
        if record.reservation != plan.reservation or not any(
            event.state == "dispatching"
            and event.operation_id == plan.operation.operation_id
            for event in record.events
        ):
            raise OwnershipConflict(
                "Failure must retain its original reservation and dispatch"
            )
        if record.state not in ("dispatching", "uncertain", "charged_failure"):
            raise InvalidTransition(
                "Failure evidence cannot replace an existing successful/released result"
            )
        charge = self._evidence.read(plan, transport_ref, control=control)
        control.checkpoint()
        response_ref: EvidenceRef | None = None
        fact_ref: EvidenceRef | None = None
        try:
            response_ref = self._evidence.response(plan, charge.body, control=control)
            fact = ModelFailureFact(
                request=plan.reservation.request,
                operation=plan.operation,
                transport_ref=transport_ref,
                response_ref=response_ref,
                provider_request_id=charge.provider_request_id,
                charge=charge.charge,
            )
            fact_ref = self._evidence.publish(fact, control=control)
            control.checkpoint()
            receipt = self._ledger.settle(
                fact.request, fact.proof(fact_ref), record.revision, op
            )
            result = FailureBillingResult(
                fact=fact, fact_ref=fact_ref, settlement=receipt
            )
            control.checkpoint()
            return result
        except BaseException as error:
            raise FailureBillingPending(
                transport_ref, response_ref, fact_ref
            ) from error
