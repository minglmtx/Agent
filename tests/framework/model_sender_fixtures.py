"""Actual CAS/budget fixtures with explicit synthetic transport and authority."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generation import (
    RequestIdentity,
    RequestRecord,
    OutcomeProof,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import (
    ModelSendPlan,
    ModelSendLimits,
    ResolvedModelRequest,
)
from lab_generate_skill.domain.model_response import ModelSendFact, ProviderReply
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.model import ModelTransport
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_file_request_ledger import UnitAuthority, NoCancel, capacity, operation, put
from test_request_budget import request


class SenderBudgetAuthority(UnitAuthority):
    def verify_outcome(
        self, record: RequestRecord, proof: OutcomeProof, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("unit proof denied")
        fact = ModelSendFact.model_validate_json(self.store.read(proof.evidence[0]))
        self.store.read(fact.response_ref)
        if fact.request != record.reservation.request or proof != fact.proof(
            proof.evidence[0]
        ):
            raise OwnershipConflict("unit provider fact mismatch")


class SendAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls = 0

    def verify(self, plan: ModelSendPlan, request: ResolvedModelRequest) -> None:
        self.calls += 1
        if self.denied or request.request != plan.reservation.request:
            raise OwnershipConflict("unit send denied")


class Transport:
    def __init__(self) -> None:
        self.calls: list[ResolvedModelRequest] = []
        self.reply_bytes = b' {"content": "hello"}\n'
        self.charge: Money | None = Money(units=2)
        self.error: BaseException | None = None
        self.reply_request: str | None = None

    def validate(self, request: ResolvedModelRequest, op: OperationContext) -> None:
        ResolvedModelRequest.model_validate(request)

    def send(
        self, request: ResolvedModelRequest, op: OperationContext
    ) -> ProviderReply:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return ProviderReply(
            request_id=self.reply_request or request.request.request_id,
            provider_request_id="unit-provider-1",
            raw_response=self.reply_bytes,
            charge=self.charge,
        )


def sender(
    root: Path,
    plan: ModelSendPlan,
    transport: ModelTransport,
    *,
    store: EvidenceStore | None = None,
    ledger: RequestLedger | None = None,
    authority: SendAuthority | None = None,
) -> LedgerModelSender:
    actual = FileEvidenceStore(root / "evidence")
    controls = OperationGuards(SystemClock(), NoCancel())
    budget = ledger or FileRequestLedger(
        root / "ledger",
        plan.reservation.scope.authorization,
        capacity(),
        controls,
        actual,
        SenderBudgetAuthority(actual),
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
    )
    return LedgerModelSender(
        budget, transport, store or actual, controls, authority or SendAuthority()
    )


@dataclass
class SendFixture:
    root: Path
    store: FileEvidenceStore
    plan: ModelSendPlan
    transport: Transport
    authority: SendAuthority
    ledger: FileRequestLedger

    def sender(
        self, *, store: EvidenceStore | None = None, ledger: RequestLedger | None = None
    ) -> LedgerModelSender:
        return sender(
            self.root,
            self.plan,
            self.transport,
            store=store,
            ledger=ledger or self.ledger,
            authority=self.authority,
        )

    def cleanup(self) -> OperationContext:
        return OperationContext.model_validate(
            operation(self.plan.reservation.request, cleanup=True).model_copy(
                update={"parent_operation_id": self.plan.operation.operation_id}
            )
        )


def send_fixture(root: Path) -> SendFixture:
    (root / "evidence").mkdir()
    (root / "ledger").mkdir()
    store = FileEvidenceStore(root / "evidence")
    auth = BudgetAuthorization(
        authorization_id="authorization",
        authorization_ref=put(store, {"unit_authorization": True}),
        ceiling=Money(units=10),
        budgets=(BudgetLimit(budget_id="a", ceiling=Money(units=7)),),
    )

    def data(raw: bytes, schema: str) -> EvidenceRef:
        return store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-fixture",
            ),
        )

    inputs = data(
        b'{"messages":[{"role":"user","content":"hi"}]}', "actor-model-input/1"
    )
    params = data(b'{"temperature":0}', "model-parameters/1")
    identity = RequestIdentity.model_validate(
        request().model_copy(
            update={
                "role": "actor",
                "attempt_id": "attempt",
                "input_sha256": inputs.sha256,
                "parameters_sha256": params.sha256,
            }
        )
    )
    op = operation(identity)
    plan = ModelSendPlan(
        reservation=Reservation(
            scope=BudgetScope(authorization=auth, budget_id="a"),
            request=identity,
            ceiling=Money(units=4),
        ),
        input_ref=inputs,
        parameters_ref=params,
        limits=ModelSendLimits(
            max_input_bytes=1024, max_parameters_bytes=1024, max_response_bytes=1024
        ),
        reserve_operation=operation(identity),
        operation=op,
        settlement_operation=OperationContext.model_validate(
            operation(identity, cleanup=True).model_copy(
                update={"parent_operation_id": op.operation_id}
            )
        ),
    )
    ledger = FileRequestLedger(
        root / "ledger",
        auth,
        capacity(),
        OperationGuards(SystemClock(), NoCancel()),
        store,
        SenderBudgetAuthority(store),
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
    )
    return SendFixture(root, store, plan, Transport(), SendAuthority(), ledger)
