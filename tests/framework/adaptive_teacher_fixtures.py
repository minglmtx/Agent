"""Original recorded read loop into real Teacher ports; explicit unit rights."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.bootstrap.teacher_attempt import (
    native_teacher_attempt,
    native_teacher_attempt_review,
)
from lab_generate_skill.application.teacher_attempt import TeacherAttemptDeps
from lab_generate_skill.application.teacher_attempt_review import (
    TeacherAttemptReviewDeps,
)
from lab_generate_skill.domain.actor_run import ActorStop
from lab_generate_skill.domain.evaluation import Evaluation, CheckResult
from lab_generate_skill.domain.teacher_attempt import (
    TeacherAttemptInput,
    TeacherFeedbackPolicy,
)
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from adaptive_actor_loop_fixtures import adaptive_loop_case, AdaptiveLoopCase
from teacher_attempt_fixtures import UnitNativeAuthority, UnitTraceAuthority, put
from retrieval_fixtures import reference
from test_run_journal import command


@dataclass
class AdaptiveTeacherCase:
    actor: AdaptiveLoopCase
    original: TeacherAttemptInput
    deps: TeacherAttemptDeps
    review: TeacherAttemptReviewDeps


def adaptive_teacher_case(root: Path, *, mode: str = "read") -> AdaptiveTeacherCase:
    c = adaptive_loop_case(root, mode=mode)
    snapshot = c.runner.run(c.request)
    trace = snapshot.project().sealed
    assert trace is not None
    store = c.base.base.loop.store
    controls = c.base.base.loop.journal.controls
    stop = ActorStop.model_validate_json(store.read(trace.stop_evidence_ref))
    secret = reference(
        {"private_reference_answer": "NOT_FOR_MODEL"},
        "unit-hidden-answer/1",
        store=store,
    )
    status: Literal["success", "unknown"] = "success" if mode == "read" else "unknown"
    evaluation = Evaluation(
        identity=c.request.scope.task,
        attempt_id=c.request.scope.attempt_id,
        contract_ref=secret,
        evaluator_id="synthetic-loop-teacher-fixture",
        evaluator_version="1",
        status=status,
        reward=1 if status == "success" else None,
        checks=(
            CheckResult(
                name="unit_goal",
                status="pass" if status == "success" else "unknown",
                reason_code="UNIT_PRIVATE_DIAGNOSTIC",
                evidence=(secret,) if status == "success" else (),
            ),
        ),
        reason_code="UNIT_PRIVATE_DIAGNOSTIC",
        evidence=(secret,),
    )
    op = command("teacher-original-read-loop", attempt=None)
    original = TeacherAttemptInput(
        scope=TeacherContextScope(
            owner=c.request.scope.owner,
            task=c.request.scope.task,
            context_id=c.request.scope.context_id,
        ),
        candidate_slot=0,
        actor_request_ref=stop.request_ref,
        trace_ref=put(store, trace),
        evaluation_ref=put(store, evaluation),
        feedback=TeacherFeedbackPolicy(
            policy_id="unit-allowed-read-feedback",
            authorization_ref=reference(
                {"unit_source_only": True},
                "teacher-feedback-authorization/1",
                store=store,
            ),
            check_names=("unit_goal",),
        ),
        operation=op,
    )
    authority = UnitNativeAuthority()
    observations = EvidenceObservations(store, controls)
    traces = EvidenceTraceRecords(store, controls, UnitTraceAuthority())
    c.base.base.client.close(
        controls.bind(command("close-teacher-read-loop-worker", attempt="attempt"))
    )
    return AdaptiveTeacherCase(
        c,
        original,
        native_teacher_attempt(store, observations, traces, authority),
        native_teacher_attempt_review(store, observations, traces, authority),
    )
