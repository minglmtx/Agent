"""Original CAS/RequestLedger/sender with synthetic source, byte-tokens and HTTP.

No provider/tokenizer capability qualification or model/source/paid request.
All costs are explicit synthetic nanodollars. Only the actual existing sender
owns reserve/dispatch/settle; the Teacher adapter adds no writable request state.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from construction_storage_fixtures import StorageFixture
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherChatMessage,
    native_evidence,
)
from lab_generate_skill.domain.teacher_json import json_text, json_value
from pathlib import Path
from lab_generate_skill.domain.budget import (
    BudgetAuthorization,
    BudgetLimit,
    BudgetScope,
    Money,
)
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.domain.generation import RequestIdentity, Reservation
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.construction_inputs import RevisionInput
from lab_generate_skill.domain.construction import ConstructionCall
from lab_generate_skill.domain.model_request import (
    ModelSendPlan,
    ModelSendLimits,
    ResolvedModelRequest,
)
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_response import ProviderReply
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.application.context_preparation import (
    ContextPreparationDeps,
    prepare_context,
)
from lab_generate_skill.adapters.models.openrouter_request import prepare_openrouter
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
    publish_teacher_revision,
)
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher
from lab_generate_skill.application.teacher_revision import RecordedTeacher
from context_budget_fixtures import profile
from context_preparation_fixtures import UnitAuthority
from teacher_context_fixtures import (
    teacher_projection_case,
    UnitTeacherCounts,
    UnitTeacherCountReview,
)
from evidence_control_fixtures import EvidenceFixtureStore
from model_sender_fixtures import SenderBudgetAuthority, SendAuthority, Transport
from test_file_request_ledger import capacity, NoCancel
from state_contract_fixtures import op
from test_actor_protocol import turn


class WholeWireCounts(UnitTeacherCounts):
    def __init__(
        self, store: EvidenceFixtureStore, builder: Callable[[bytes, str], bytes]
    ) -> None:
        super().__init__(store)
        self.builder = builder

    def wire(self, raw: bytes, model: str) -> bytes:
        return self.builder(raw, model)


class WholeWireReview(UnitTeacherCountReview):
    def __init__(
        self, store: EvidenceReader, builder: Callable[[bytes, str], bytes]
    ) -> None:
        super().__init__(store)
        self.builder = builder

    def wire(self, raw: bytes, model: str) -> bytes:
        return self.builder(raw, model)


class UnitTeacherTransport(Transport):
    def validate(self, request: ResolvedModelRequest, op: OperationContext) -> None:
        prepare_openrouter(request)

    def send(
        self, request: ResolvedModelRequest, op: OperationContext
    ) -> ProviderReply:
        return super().send(request, op)


@dataclass
class TeacherRevisionCase:
    store: EvidenceFixtureStore
    plan: TeacherRevisionPlan
    plans: EvidenceTeacherRevisionPlans
    ledger: FileRequestLedger
    transport: UnitTeacherTransport
    source: SendAuthority
    context: UnitAuthority
    counts: WholeWireCounts
    count_review: WholeWireReview
    teacher: RecordedTeacher
    controls: OperationGuards
    policy: ContextProjectionPolicy
    plan_ref: EvidenceRef
    wire: Callable[[bytes, str], bytes]


def revision_case(
    root: Path,
    site: Site = "map",
    *,
    construction: StorageFixture | None = None,
    parameter_seed: int | None = 44,
    parameter_output_tokens: int = 17,
) -> TeacherRevisionCase:
    root.mkdir()
    (root / "evidence").mkdir()
    (root / "ledger").mkdir()
    store = (
        construction.store
        if construction is not None
        else EvidenceFixtureStore(root / "evidence")
    )
    original = teacher_projection_case(site)
    if construction is not None:
        public = PublicConstructionContext.model_validate_json(
            store.read(construction.plan.public_context_ref)
        )
        state = original.allowed.scope.model_copy(
            update={
                "owner": construction.plan.run.owner,
                "task": public.task.identity,
                "context_id": public.context_id,
            }
        )
        body = native_evidence(original.allowed.messages[1].content)
        body["task"] = public.task.goal
        body["public_task"] = json_value(public.task.model_dump(mode="json"))
        allowed = AllowedTeacherEvidence(
            scope=state,
            task=public.task,
            teacher_round=3,
            messages=(
                original.allowed.messages[0],
                TeacherChatMessage(role="user", content=json_text(body)),
            ),
        )
        original = replace(
            original,
            allowed=allowed,
            raw=allowed.model_dump_json().encode(),
            source=original.source.model_copy(update={"scope": state}),
        )
    execute = op("original-teacher-3-send").model_copy(update={"attempt_id": None})
    controls = OperationGuards(SystemClock(), NoCancel())
    control = controls.bind(execute)

    def put(raw: bytes, schema: str, visibility: str = "private") -> EvidenceRef:
        return store.put(
            raw,
            EvidenceMetadata.model_validate(
                dict(
                    media_type="application/json",
                    content_schema=schema,
                    visibility=visibility,
                    producer="unit-original-teacher",
                )
            ),
            control,
        )

    auth = BudgetAuthorization(
        authorization_id="authorization",
        authorization_ref=put(b'{"unit_authorization":true}', "unit-authorization/1"),
        ceiling=Money(units=10),
        budgets=(BudgetLimit(budget_id="a", ceiling=Money(units=7)),),
    )
    budget = BudgetScope(authorization=auth, budget_id="a")
    fee_ref = put(budget.model_dump_json().encode(), "budget-scope/1")
    params = json.dumps(
        dict(
            max_tokens=17,
            reasoning={"effort": "medium"},
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "compact_skill",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string"}
                            for key in ("title", "principle", "when_to_apply")
                        },
                        "required": ["title", "principle", "when_to_apply"],
                        "additionalProperties": False,
                    },
                },
            },
            provider={
                "allow_fallbacks": False,
                "require_parameters": True,
                "only": ["unit-test-provider"],
            },
        ),
        separators=(",", ":"),
    ).encode()
    actual_parameters = json.loads(params)
    actual_parameters["max_tokens"] = parameter_output_tokens
    if parameter_seed is not None:
        actual_parameters["seed"] = parameter_seed
    params = json.dumps(actual_parameters, separators=(",", ":")).encode()
    params_ref = put(params, "model-parameters/1")
    model_ref = put(
        b'{"schema_version":"unit-teacher-binding/1","model":"unit-teacher-full-wire","provider":"openrouter"}',
        "model-binding/1",
    )
    if construction is not None:
        model_ref = next(
            m.model_binding_ref for m in construction.plan.models if m.role == "teacher"
        )
    limits = ModelSendLimits(
        max_input_bytes=64 * 1024**2,
        max_parameters_bytes=1024**2,
        max_response_bytes=1024**2,
    )

    def identity(raw: bytes, model: str) -> RequestIdentity:
        return RequestIdentity(
            request_id="teacher-3-original",
            authorization_id="authorization",
            budget_id="a",
            owner=original.allowed.scope.owner,
            task=original.allowed.task.identity,
            attempt_id=None,
            candidate_index=6,
            revision_index=3,
            role="teacher",
            logical_index=0,
            provider_id="openrouter",
            model_id=model,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            parameters_sha256=params_ref.sha256,
        )

    def wire(raw: bytes, model: str) -> bytes:
        return prepare_openrouter(
            ResolvedModelRequest(
                request=identity(raw, model),
                input_bytes=raw,
                parameters_bytes=params,
                limits=limits,
            )
        )

    source_ref = put(original.raw, "teacher-input/1", "teacher")
    source = original.source.model_copy(update={"allowed_input_ref": source_ref})
    policy = original.policy.model_copy(
        update={
            "software_evidence_ref": put(
                b'{"synthetic_projection_qualification_only":true}',
                "context-policy-evidence/1",
            )
        }
    )
    budget_profile = profile(
        "teacher",
        model="unit-teacher-full-wire",
        provider="openrouter",
        routing_ref=model_ref,
        configuration_ref=params_ref,
        context_window=100017,
        input_limit=100000,
        output_reserve=17,
        soft_target=85000,
        fee_scope_ref=fee_ref,
        counting_method="unit-full-openrouter-wire-byte-tokens",
    )
    preparation = ContextPreparationRequest(
        schema_version="context-preparation-request/2",
        scope=source.scope,
        operation=execute,
        request_id="teacher-3-original",
        source=source,
        profile=budget_profile,
        policy=policy,
    )
    context = UnitAuthority()
    project, protection = build_teacher_context(policy)
    counts = WholeWireCounts(store, wire)
    prepared = prepare_context(
        preparation,
        ContextPreparationDeps(store, context, project, protection, counts),
        control=control,
    )
    assert prepared.selected_input_ref is not None
    revision = RevisionInput(
        request_id="teacher-3-original",
        teacher_round=3,
        seed=44,
        projection_ref=source_ref,
    )
    revision_ref = put(
        revision.model_dump_json().encode(), "revision-input/1", "teacher"
    )
    call = ConstructionCall(
        request_id=revision.request_id,
        role="teacher",
        candidate_slot=6,
        resample_index=0,
        seed=44,
        temperature=None,
        model_binding_ref=model_ref,
        base_parameters_ref=(
            next(
                m.parameters_ref
                for m in construction.plan.models
                if m.role == "teacher"
            )
            if construction is not None
            else params_ref
        ),
        input_ref=revision_ref,
        parameters_ref=params_ref,
    )
    request = identity(
        store.read(prepared.selected_input_ref, control), budget_profile.model
    )
    send = ModelSendPlan(
        reservation=Reservation(scope=budget, request=request, ceiling=Money(units=4)),
        input_ref=prepared.selected_input_ref,
        parameters_ref=params_ref,
        limits=limits,
        reserve_operation=execute.model_copy(
            update={"operation_id": "teacher-3-original-reserve"}
        ),
        operation=execute,
        settlement_operation=execute.cleanup(
            "teacher-3-original-settle", now=execute.deadline, seconds=30
        ),
    )
    plan = TeacherRevisionPlan(
        revision=revision,
        call=call,
        preparation=preparation,
        prepared=prepared,
        send=send,
        reasoning_accounting="completion_includes_reasoning",
    )
    plan_ref = publish_teacher_revision(plan, store, control=control)
    plans = EvidenceTeacherRevisionPlans({revision.request_id: plan_ref}, store)
    ledger = FileRequestLedger(
        root / "ledger",
        auth,
        capacity(),
        controls,
        store,
        SenderBudgetAuthority(store),
        dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
    )
    transport = UnitTeacherTransport()
    transport.reply_bytes = json.dumps(
        dict(
            id="unit-provider-1",
            choices=[
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(turn().skill.model_payload()),
                    },
                }
            ],
            usage={
                "cost": 2e-9,
                "prompt_tokens": 100,
                "completion_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        ),
        separators=(",", ":"),
    ).encode()
    authority = SendAuthority()
    count_review = WholeWireReview(store, wire)
    teacher = recorded_teacher(
        plans,
        policy,
        ledger=ledger,
        transport=transport,
        evidence=store,
        controls=controls,
        source_authority=authority,
        context_authority=context,
        counts=count_review,
    )
    return TeacherRevisionCase(
        store,
        plan,
        plans,
        ledger,
        transport,
        authority,
        context,
        counts,
        count_review,
        teacher,
        controls,
        policy,
        plan_ref,
        wire,
    )
