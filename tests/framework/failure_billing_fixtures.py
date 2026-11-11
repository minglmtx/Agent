"""Synthetic provider authority for actual error CAS/budget integration tests."""

from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.adapters.models.failure_evidence import FailureEvidence
from lab_generate_skill.adapters.models.failure_billing import LedgerFailureBilling
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generation import (
    RequestIdentity,
    RequestRecord,
    OutcomeProof,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_failure import ModelFailureFact
from lab_generate_skill.domain.model_response import ModelSendUnconfirmed
from lab_generate_skill.domain.model_request import ModelSendPlan
from lab_generate_skill.runtime.lifecycle import OperationGuards
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from model_sender_fixtures import SenderBudgetAuthority, SendFixture
from openrouter_fixtures import fixture as http_fixture, provider, transport
from test_file_request_ledger import NoCancel, capacity

FAILURE = b'{"id":"unit-error","error":{"message":"unit failure"},"usage":{"cost":0.000000002}}'


class FailureAuthority(SenderBudgetAuthority):
    def __init__(self, store: FileEvidenceStore, plan: ModelSendPlan) -> None:
        super().__init__(store)
        self.plan = plan

    def verify_outcome(
        self, record: RequestRecord, proof: OutcomeProof, op: OperationContext
    ) -> None:
        if proof.outcome != "charged_failure":
            return super().verify_outcome(record, proof, op)
        if self.denied:
            raise OwnershipConflict("unit failure bill denied")
        fact = ModelFailureFact.model_validate_json(self.store.read(proof.evidence[0]))
        charge = FailureEvidence(self.store).read(
            self.plan,
            fact.transport_ref,
            OperationGuards(SystemClock(), NoCancel()).bind(op),
        )
        if (
            fact.request != record.reservation.request
            or fact.operation != self.plan.operation
            or (
                fact.provider_request_id != charge.provider_request_id
                or fact.charge != charge.charge
                or self.store.read(fact.response_ref) != charge.body
                or fact.proof(proof.evidence[0]) != proof
            )
        ):
            raise OwnershipConflict(
                "unit failure bill differs from original provider evidence"
            )


def fixture(root: Path) -> tuple[SendFixture, FailureAuthority]:
    f = http_fixture(root)
    authority = FailureAuthority(f.store, f.plan)
    f.ledger = FileRequestLedger(
        root / "ledger",
        f.plan.reservation.scope.authorization,
        capacity(),
        OperationGuards(SystemClock(), NoCancel()),
        f.store,
        authority,
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
    )
    return f, authority


def fail_send(f: SendFixture, body: bytes = FAILURE, status: int = 200) -> EvidenceRef:
    with provider() as server:
        server.body, server.status = body, status
        sender = LedgerModelSender(
            f.ledger,
            transport(f, server.endpoint),
            f.store,
            OperationGuards(SystemClock(), NoCancel()),
            f.authority,
        )
        try:
            sender.generate(f.plan)
        except ModelSendUnconfirmed as error:
            assert len(server.requests) == 1 and error.transport_ref is not None
            return error.transport_ref
        raise AssertionError("Expected original provider failure")


def reconciler(f: SendFixture) -> LedgerFailureBilling:
    return LedgerFailureBilling(
        f.ledger, f.store, OperationGuards(SystemClock(), NoCancel())
    )


def other_request(f: SendFixture, name: str = "other") -> RequestIdentity:
    original = f.plan.reservation.request
    return RequestIdentity.model_validate(
        original.model_copy(
            update={
                "request_id": name,
                "owner": original.owner.model_copy(
                    update={"run_id": name, "worker_id": name}
                ),
            }
        )
    )
