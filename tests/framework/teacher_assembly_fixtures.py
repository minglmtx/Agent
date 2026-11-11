"""Original native-source/file history/paid ledger, explicit synthetic rights.

No actual provider, source admission, tokenizer, credits, model, or site request.
The budget is the original RunPlan budget, not a replacement test authorization.
"""

import hashlib, json
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Generic, TypeVar
from lab_generate_skill.adapters.ledger.request_ledger import FileRequestLedger
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.models.openrouter_request import prepare_openrouter
from lab_generate_skill.adapters.models.teacher_response import OpenRouterTeacherDecoder
from lab_generate_skill.application.context_preparation import (
    ContextPreparationDeps,
    prepare_context,
)
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.application.teacher_assembly import TeacherAssemblyDeps
from lab_generate_skill.application.teacher_assembly_review import (
    TeacherAssemblyReviewDeps,
)
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.bootstrap.teacher_source import teacher_source_authority
from lab_generate_skill.bootstrap.teacher_assembly import (
    teacher_assembly_dependencies,
    teacher_assembly_review_dependencies,
)
from lab_generate_skill.domain.teacher_assembly import TeacherRevisionAssemblyInput
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction import (
    CallPlanned,
    CallCompleted,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.budget import BudgetScope, Money
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.generation import (
    RequestIdentity,
    Reservation,
    RequestRecord,
)
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import (
    ResolvedModelRequest,
    ModelSendLimits,
    ModelSendPlan,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.teacher_source import TeacherSourceAuthority
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    PublishedTeacherSource,
)
from construction_storage_fixtures import StorageFixture
from lab_generate_skill.ports.context_projection import ContextPreparationAuthority
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from teacher_native_source_fixtures import native_source_case, NativeSourceCase
from teacher_context_fixtures import teacher_projection_case
from teacher_revision_fixtures import (
    WholeWireCounts,
    WholeWireReview,
    UnitTeacherTransport,
)
from construction_storage_fixtures import UnitConstructionAuthority
from context_budget_fixtures import profile
from context_preparation_fixtures import UnitAuthority
from model_sender_fixtures import SenderBudgetAuthority, SendAuthority
from test_actor_protocol import turn


class UnitAssemblyAuthority:
    denied = False
    calls = 0

    def verify_build(
        self,
        progress: ConstructionProgress,
        original: TeacherRevisionAssemblyInput,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise OwnershipConflict(
                "Unit original construction/provider/fee admission denied"
            )
        if progress.project().next_action.kind != "revise":
            raise OwnershipConflict(
                "Original revision is not ready; pending/unknown cannot renew"
            )

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        original: TeacherRevisionAssemblyInput,
        plan: TeacherRevisionPlan,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert (
            progress.plan.task.identity == original.preparation.scope.task
            and plan.preparation == original.preparation
        )


class UnitNativeConstructionAuthority(UnitConstructionAuthority):
    """Recognize actual original Teacher wire instead of old storage-only marker."""

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("Unit original source writer denied")
        if (
            isinstance(event, CallPlanned)
            and event.call.role == "teacher"
            and event.call.request_id.startswith("original-native-revision")
        ):
            params = json.loads(self.store.read(event.call.parameters_ref))
            assert params["seed"] == event.call.seed and params["max_tokens"] == 17
            assert event.call.base_parameters_ref == next(
                m.parameters_ref for m in progress.plan.models if m.role == "teacher"
            )
            return
        if (
            isinstance(event, CallCompleted)
            and isinstance(event.response, RevisionResult)
            and event.response.schema_version == "revision-result/2"
        ):
            actual = OpenRouterTeacherDecoder().decode(
                self.store.read(event.response.response_ref)
            )
            assert actual.skill == event.response.skill
            return
        super().verify_event(progress, event, op)


class UnitOriginalBudgetAuthority(SenderBudgetAuthority):
    def __init__(self, data: StorageFixture, budget: BudgetScope) -> None:
        super().__init__(data.store)
        self.budget = budget

    def authorize_reservation(
        self, reservation: Reservation, op: OperationContext
    ) -> None:
        if self.denied or reservation.scope != self.budget:
            raise OwnershipConflict("Original budget scope changed")
        self.store.read(self.budget.authorization.authorization_ref)


class UnitOriginalSendAuthority(SendAuthority):
    def __init__(self, journal: FileConstructionJournal, request_id: str) -> None:
        super().__init__()
        self.journal, self.request_id = journal, request_id

    def verify(self, plan: ModelSendPlan, request: ResolvedModelRequest) -> None:
        super().verify(plan, request)
        pending = self.journal.read(plan.operation).project().pending_call
        if (
            pending is None
            or pending.request_id != self.request_id
            or (pending.input_ref.sha256, pending.parameters_ref, pending.seed)
            != (
                self.expected.call.input_ref.sha256,
                self.expected.call.parameters_ref,
                self.expected.revision.seed,
            )
        ):
            raise OwnershipConflict("Original live Teacher call no longer pending")

    expected: TeacherRevisionPlan


SourceT = TypeVar("SourceT")


@dataclass
class SourceAssemblyCase(Generic[SourceT]):
    source: SourceT
    original: TeacherRevisionAssemblyInput
    deps: TeacherAssemblyDeps
    review: TeacherAssemblyReviewDeps
    authority: UnitAssemblyAuthority
    ledger: FileRequestLedger
    transport: UnitTeacherTransport
    send_authority: UnitOriginalSendAuthority
    context: ContextPreparationAuthority
    counts: WholeWireCounts
    count_review: WholeWireReview
    wire: Callable[[bytes, str], bytes]


AssemblyCase = SourceAssemblyCase[NativeSourceCase]


@dataclass(frozen=True)
class AssemblySourceData:
    data: StorageFixture
    progress: ConstructionProgress
    operation: OperationContext
    bindings: TeacherSourceBindings
    source: PublishedTeacherSource
    controls: OperationControls
    observations: ObservationLoader
    retrieval: RetrievalRecords
    source_authority: TeacherSourceAuthority
    review_source: Callable[[OperationContext], TeacherSourceReviewDeps]


def assembly_case(
    root: Path,
    site: Site = "map",
    *,
    round_number: int = 1,
    parameter_seed: int | None = None,
    parameter_output_tokens: int = 17,
) -> AssemblyCase:
    c = native_source_case(root, site, recorded_teacher=True, round_number=round_number)
    material = AssemblySourceData(
        c.data,
        c.progress,
        c.operation,
        c.bindings,
        c.source,
        c.controls,
        c.observations,
        c.retrieval,
        c.source_authority,
        c.review_source,
    )
    return assembly_from_source(
        root,
        c,
        material,
        site=site,
        round_number=round_number,
        parameter_seed=parameter_seed,
        parameter_output_tokens=parameter_output_tokens,
        replace_source_authority=True,
    )


def assembly_from_source(
    root: Path,
    source: SourceT,
    c: AssemblySourceData,
    *,
    site: Site = "map",
    round_number: int = 1,
    parameter_seed: int | None = None,
    parameter_output_tokens: int = 17,
    replace_source_authority: bool = False,
) -> SourceAssemblyCase[SourceT]:
    """Prepare the same frozen original wire/ledger from explicit saved sources."""
    store = c.data.store
    control = c.controls.bind(c.operation)
    plans = EvidenceRunPlans(store, c.controls)
    run = plans.load(c.progress.plan.run, c.operation)
    assert run.budget is not None
    role = next(r for r in run.budget.roles if r.role == "teacher")
    budget = BudgetScope(
        authorization=run.budget.authorization, budget_id=role.budget_id
    )
    fee_ref = store.put(
        budget.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="budget-scope/1",
            visibility="private",
            producer="unit-original-assembly-budget",
        ),
    )
    params = json.dumps(
        dict(
            seed=(
                c.progress.plan.method.teacher_seed(round_number)
                if parameter_seed is None
                else parameter_seed
            ),
            max_tokens=parameter_output_tokens,
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
    parameters = store.put(
        params,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="model-parameters/1",
            visibility="private",
            producer="unit-original-assembly-wire",
        ),
    )
    model = next(m for m in c.progress.plan.models if m.role == "teacher")
    limits = ModelSendLimits(
        max_input_bytes=64 * 1024**2,
        max_parameters_bytes=1024**2,
        max_response_bytes=1024**2,
    )

    def wire(raw: bytes, name: str) -> bytes:
        request = RequestIdentity(
            request_id=c.bindings.request_id,
            authorization_id=budget.authorization.authorization_id,
            budget_id=budget.budget_id,
            owner=c.progress.plan.run.owner,
            task=c.progress.plan.task.identity,
            attempt_id=None,
            candidate_index=round_number + 3,
            revision_index=round_number,
            role="teacher",
            logical_index=0,
            provider_id="openrouter",
            model_id=name,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            parameters_sha256=parameters.sha256,
        )
        return prepare_openrouter(
            ResolvedModelRequest(
                request=request, input_bytes=raw, parameters_bytes=params, limits=limits
            )
        )

    policy = teacher_projection_case(site).policy
    profile_value = profile(
        "teacher",
        model=model.model,
        provider=model.provider,
        routing_ref=model.model_binding_ref,
        configuration_ref=parameters,
        context_window=400017,
        input_limit=400000,
        output_reserve=17,
        soft_target=340000,
        fee_scope_ref=fee_ref,
        counting_method="unit-full-openrouter-wire-byte-tokens",
    )
    preparation = ContextPreparationRequest(
        schema_version="context-preparation-request/2",
        scope=c.source.source.scope,
        operation=c.operation,
        request_id=c.bindings.request_id,
        source=c.source.source,
        profile=profile_value,
        policy=policy,
    )
    context = teacher_source_authority(
        UnitAuthority(),
        c.source,
        evidence=store,
        observations=c.observations,
        retrieval=c.retrieval,
        authority=c.source_authority,
        operation=c.operation,
    )
    project, protection = build_teacher_context(policy)
    counts = WholeWireCounts(store, wire)
    count_review = WholeWireReview(store, wire)
    prepared = prepare_context(
        preparation,
        ContextPreparationDeps(store, context, project, protection, counts),
        control=control,
    )
    original = TeacherRevisionAssemblyInput(
        source=c.source,
        preparation=preparation,
        prepared=prepared,
        budget=budget,
        ceiling=role.reservation_ceiling,
        limits=limits,
        reserve_operation=c.operation.model_copy(
            update={"operation_id": c.operation.operation_id + "-reserve"}
        ),
        settlement_operation=c.operation.cleanup(
            c.operation.operation_id + "-settle", now=c.operation.deadline, seconds=60
        ),
        reasoning_accounting="completion_includes_reasoning",
    )
    authority = UnitAssemblyAuthority()
    if replace_source_authority:
        c.data.authority = UnitNativeConstructionAuthority(store)
    journal = c.data.journal()
    review_context = ContextReviewDeps(
        store, context, project, protection, count_review
    )
    deps = teacher_assembly_dependencies(
        store,
        journal,
        c.review_source(c.operation),
        review_context,
        authority,
        plans=plans,
    )
    review = teacher_assembly_review_dependencies(
        store,
        journal,
        c.review_source(c.operation),
        review_context,
        authority,
        plans=plans,
    )
    (root / "paid-ledger").mkdir()
    ledger = FileRequestLedger(
        root / "paid-ledger",
        run.budget.authorization,
        run.budget.capacity,
        c.controls,
        store,
        UnitOriginalBudgetAuthority(c.data, budget),
        dispatch_policy=run.budget.dispatch_policy,
    )
    transport = UnitTeacherTransport()
    skill = turn().skill.model_copy(
        update={"title": "Teacher revised original round " + str(round_number)}
    )
    transport.reply_bytes = json.dumps(
        dict(
            id="unit-provider-1",
            choices=[
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(skill.model_payload()),
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
    sender = UnitOriginalSendAuthority(journal, c.bindings.request_id)
    return SourceAssemblyCase(
        source,
        original,
        deps,
        review,
        authority,
        ledger,
        transport,
        sender,
        context,
        counts,
        count_review,
        wire,
    )
