"""Real files and strict fixture facts, explicitly not production authority."""

import json
from dataclasses import dataclass
from pathlib import Path
import pytest

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.domain.claims import SourceClaimBinding
from claim_fixtures import UnitClaimAuthority
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    AttemptResolved,
    CallCompleted,
    CallPlanned,
    CallUncertain,
    ConstructionPlan,
    ProgressEvent,
    SelectionCommitted,
)
from lab_generate_skill.domain.construction_inputs import (
    GenerationInput,
    PublicConstructionContext,
    RevisionInput,
)
from lab_generate_skill.domain.construction_journal import ConstructionCapacity
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    select_target,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evaluation import CheckResult, Evaluation
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan, ConstructionWorkload
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.domain.retrieval import RetrievalResult
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.runtime.lifecycle import OperationGuards

from test_evidence_run_plans import persisted_plan
from test_construction_state import (
    completed_attempt,
    completed_call,
    planned_attempt,
    planned_call,
)
from test_run_journal import CancelSwitch, command
from test_run_plan import binding
from context_storage_fixtures import fixture as context_fixture, UnitContextAuthority
import state_contract_fixtures as state_contracts
from retrieval_fixtures import fixture as retrieval_fixture
from test_retrieval_evidence import UnitAuthority as UnitRetrievalAuthority


def put(
    store: FileEvidenceStore,
    value: object,
    schema: str = "unit-construction/1",
    visibility: str = "private",
) -> EvidenceRef:
    raw = (
        value.model_dump_json().encode()
        if isinstance(value, Contract)
        else json.dumps(value, sort_keys=True).encode()
    )
    return store.put(
        raw,
        EvidenceMetadata.model_validate(
            dict(
                media_type="application/json",
                content_schema=schema,
                visibility=visibility,
                producer="unit-construction",
            )
        ),
    )


def limits(**changes: int) -> ConstructionCapacity:
    values = dict(max_events=256, max_bytes=4 * 1024 * 1024, max_event_bytes=32768)
    values.update(changes)
    return ConstructionCapacity.model_validate(values)


class UnitConstructionAuthority:
    """Validates exact stored fixture facts; never used by production bootstrap."""

    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.denied = False

    def verify_plan(self, plan: ConstructionPlan, op: OperationContext) -> None:
        if self.denied:
            raise OwnershipConflict("Unit claim rejected")

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("Unit writer rejected")
        if isinstance(event, CallPlanned):
            call = event.call
            if json.loads(self.store.read(call.parameters_ref)) != {
                "seed": call.seed,
                "temperature": call.temperature,
            }:
                raise OwnershipConflict("Unit actual parameters changed")
        if isinstance(event, CallCompleted):
            result = event.response
            expected = {
                "request_id": result.request_id,
                "input_sha256": result.input_sha256,
                "parameters_sha256": result.parameters_sha256,
                "skill": result.skill.model_payload(),
            }
            if json.loads(self.store.read(result.response_ref)) != expected:
                raise OwnershipConflict("Unit provider response changed")
        if isinstance(event, (AttemptCompleted, AttemptResolved)):
            attempt_result = event.result
            expected_attempt = {
                "intent": attempt_result.intent.model_dump(mode="json"),
                "interactions": attempt_result.interactions,
                "generations": attempt_result.generations,
                "unit_closed": True,
            }
            if (
                json.loads(self.store.read(attempt_result.attempt_ref))
                != expected_attempt
            ):
                raise OwnershipConflict("Unit attempt execution facts changed")
        if isinstance(event, CallUncertain):
            if json.loads(self.store.read(event.evidence_ref)) != {
                "unknown_request": event.request_id
            }:
                raise OwnershipConflict("Unit uncertainty changed")


@dataclass
class StorageFixture:
    root: Path
    store: FileEvidenceStore
    plan: ConstructionPlan
    authority: UnitConstructionAuthority
    context_authority: UnitContextAuthority
    retrieval_authority: UnitRetrievalAuthority
    claim_authority: UnitClaimAuthority

    def claims(self) -> FileSourceClaims:
        controls = OperationGuards(SystemClock(), CancelSwitch())
        return FileSourceClaims(
            self.root / "claims",
            "unit-scope",
            controls,
            self.store,
            EvidenceRunPlans(self.store, controls),
            self.claim_authority,
        )

    def journal(
        self,
        capacity: ConstructionCapacity | None = None,
        plan: ConstructionPlan | None = None,
        teacher_review: TeacherConstructionVerifier | None = None,
    ) -> FileConstructionJournal:
        controls = OperationGuards(SystemClock(), CancelSwitch())
        return FileConstructionJournal(
            self.root / "journal",
            plan or self.plan,
            capacity or limits(),
            controls,
            self.store,
            EvidenceRunPlans(self.store, controls),
            self.authority,
            EvidenceContextRecords(self.store, controls, self.context_authority),
            EvidenceRetrievalRecords(self.store, controls, self.retrieval_authority),
            self.claims(),
            teacher_review=teacher_review,
        )

    def event(
        self,
        progress: ConstructionProgress,
        *,
        status: str = "failure",
        request_suffix: str = "",
    ) -> ProgressEvent:
        view = progress.project()
        action = view.next_action
        if action.kind in ("generate", "revise"):
            base = planned_call(progress)
            call = base.call
            request_id = call.request_id + request_suffix
            if call.role == "generator":
                context = PublicConstructionContext.model_validate_json(
                    self.store.read(self.plan.public_context_ref)
                )
                retrieved_result = RetrievalResult.model_validate_json(
                    self.store.read(self.plan.retrieval_ref)
                )
                skills = tuple(
                    CompactSkill.model_validate_json(self.store.read(hit.skill_ref))
                    for hit in retrieved_result.hits
                )
                assert call.temperature is not None
                request = GenerationInput(
                    request_id=request_id,
                    context=context,
                    retrieved_skills=skills,
                    candidate_index=call.candidate_slot,
                    resample_index=call.resample_index,
                    seed=call.seed,
                    temperature=call.temperature,
                )
                input_ref = put(self.store, request, "generation-input/1", "public")
            else:
                projection = put(
                    self.store, {"unit_projection": True}, "teacher-input/1", "teacher"
                )
                revision = RevisionInput(
                    request_id=request_id,
                    teacher_round=call.candidate_slot - 3,
                    seed=call.seed,
                    projection_ref=projection,
                )
                input_ref = put(self.store, revision, "revision-input/1", "teacher")
            parameters = put(
                self.store, {"seed": call.seed, "temperature": call.temperature}
            )
            return CallPlanned(
                operation=base.operation,
                call=call.model_copy(
                    update={
                        "request_id": request_id,
                        "input_ref": input_ref,
                        "parameters_ref": parameters,
                    }
                ),
            )
        if action.kind == "await_response":
            event = completed_call(progress)
            response = event.response
            raw = put(
                self.store,
                {
                    "request_id": response.request_id,
                    "input_sha256": response.input_sha256,
                    "parameters_sha256": response.parameters_sha256,
                    "skill": response.skill.model_payload(),
                },
            )
            return CallCompleted(
                operation=event.operation,
                response=response.model_copy(update={"response_ref": raw}),
            )
        if action.kind == "execute":
            return planned_attempt(progress)
        if action.kind == "await_attempt":
            attempt_event = completed_attempt(progress, status)
            result = attempt_event.result
            fact = put(self.store, {"unit_goal": status})
            checks = tuple(
                CheckResult.model_validate(
                    item.model_copy(update={"evidence": (fact,)})
                )
                for item in result.evaluation.checks
            )
            evaluation = Evaluation.model_validate(
                result.evaluation.model_copy(
                    update={"contract_ref": fact, "checks": checks}
                )
            )
            evaluation_ref = put(self.store, evaluation, "evaluation/1")
            execution = put(
                self.store,
                {
                    "intent": result.intent.model_dump(mode="json"),
                    "interactions": result.interactions,
                    "generations": result.generations,
                    "unit_closed": True,
                },
                "attempt-result/1",
            )
            return AttemptCompleted(
                operation=attempt_event.operation,
                result=result.model_copy(
                    update={
                        "evaluation": evaluation,
                        "evaluation_ref": evaluation_ref,
                        "attempt_ref": execution,
                    }
                ),
            )
        if action.kind == "select":
            return SelectionCommitted(
                operation=command(), selection=select_target(view.attempts)
            )
        raise AssertionError(action)


def fixture(
    root: Path,
    *,
    recorded_teacher: bool = False,
    site: Site = "map",
    allowed_actions: tuple[str, ...] = ("stop",),
) -> StorageFixture:
    (root / "evidence").mkdir()
    (root / "journal").mkdir()
    (root / "claims").mkdir()
    store = FileEvidenceStore(root / "evidence")
    run = persisted_plan(store)
    if recorded_teacher:
        run = RunPlan.model_validate(
            run.model_copy(
                update={
                    "models": tuple(
                        (
                            model.model_copy(
                                update={
                                    "provider": "openrouter",
                                    "model": "unit-teacher-full-wire",
                                }
                            )
                            if model.role == "teacher"
                            else model
                        )
                        for model in run.models
                    )
                }
            )
        )
    if site != run.tasks[0].identity.site:
        run = RunPlan.model_validate(
            run.model_copy(
                update={
                    "tasks": tuple(
                        task.model_copy(
                            update={
                                "identity": task.identity.model_copy(
                                    update={"site": site}
                                )
                            }
                        )
                        for task in run.tasks
                    )
                }
            )
        )
    task_identity = run.tasks[0].identity
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(state_contracts, "identity", lambda: task_identity)
        context_data = context_fixture(
            root / "evidence", allowed_actions=allowed_actions
        )
    store = context_data.store
    task = context_data.inputs.source_inputs.baseline_inputs.binding
    retrieved = retrieval_fixture(
        store, public_context=context_data.inputs.source_inputs.context
    )
    assert isinstance(run.workload, ConstructionWorkload)
    run = RunPlan.model_validate(
        run.model_copy(
            update={
                "tasks": (task,),
                "split_manifest_ref": retrieved.scope.split_ref,
                "workload": run.workload.model_copy(
                    update={"bank_ref": retrieved.scope.bank_ref}
                ),
            }
        )
    )
    controls = OperationGuards(SystemClock(), CancelSwitch())
    run_ref = EvidenceRunPlans(store, controls).publish(run, command())
    bound = RunBinding.model_validate(
        binding(run).model_copy(
            update={
                "plan_ref": run_ref,
                "owner": context_data.inputs.source.scope.owner,
            }
        )
    )
    context_ref = context_data.inputs.source.public_context_ref
    qualification = context_data.adapter.publish_context(
        context_data.inputs.source, context_data.inputs.source.operation
    )
    retrieval_authority = UnitRetrievalAuthority(store)
    retrieval = EvidenceRetrievalRecords(store, controls, retrieval_authority).publish(
        retrieved.result, command()
    )
    claim_authority = UnitClaimAuthority()
    claim = FileSourceClaims(
        root / "claims",
        "unit-scope",
        controls,
        store,
        EvidenceRunPlans(store, controls),
        claim_authority,
    ).claim(SourceClaimBinding(scope_id="unit-scope", run=bound, task=task), command())
    plan = ConstructionPlan.from_run_plan(
        run,
        bound,
        "task",
        claim_ref=claim.reference,
        public_context_ref=context_ref,
        context_receipt_ref=qualification,
        retrieval_ref=retrieval,
        retrieval_scope=retrieved.scope,
    )
    return StorageFixture(
        root,
        store,
        plan,
        UnitConstructionAuthority(store),
        context_data.authority,
        retrieval_authority,
        claim_authority,
    )
