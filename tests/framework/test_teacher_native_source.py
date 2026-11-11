"""Native parts -> original construction source/common preparation/closed review.

Real typed originals/CAS/journals and original Actor native service software are
used; source/provider/allocations remain explicit synthetic test permissions.
"""

from pathlib import Path
from dataclasses import replace
import pytest
from lab_generate_skill.application.teacher_attempt import publish_teacher_attempt
from lab_generate_skill.application.teacher_attempt_review import review_teacher_attempt
from lab_generate_skill.application.teacher_source import (
    publish_teacher_source,
    TeacherSourceUnconfirmed,
)
from lab_generate_skill.application.teacher_source_review import (
    review_teacher_source,
    TeacherSourceReviewDeps,
)
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationDeps,
)
from lab_generate_skill.application.context_review import (
    review_context,
    ContextReviewDeps,
)
from lab_generate_skill.bootstrap.teacher_attempt import (
    native_teacher_attempt,
    native_teacher_attempt_review,
    native_teacher_source_authority,
)
from lab_generate_skill.bootstrap.teacher_source import (
    teacher_source_dependencies,
    teacher_source_authority,
)
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.domain.actor_run import ActorStop
from lab_generate_skill.domain.construction import AttemptCompleted
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherModelInput,
    native_evidence,
)
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherAttemptView,
)
from lab_generate_skill.domain.teacher_json import object_value, array_value
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.evaluation import Evaluation, CheckResult
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.clock import SystemClock
from teacher_attempt_fixtures import (
    native_attempt_case,
    UnitNativeAuthority,
    UnitTraceAuthority,
    put,
)
from teacher_source_fixtures import UnitTeacherSourceAuthority
from construction_storage_fixtures import fixture
from teacher_context_fixtures import (
    teacher_projection_case,
    UnitTeacherCounts,
    UnitTeacherCountReview,
)
from context_budget_fixtures import profile
from context_preparation_fixtures import UnitAuthority
from test_run_journal import command, CancelSwitch
from datetime import datetime, timezone


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_all_four_native_attempts_original_journal_prepare_and_independent_closed_review(
    tmp_path: Path, site: Site
) -> None:
    from teacher_native_source_fixtures import native_source_case

    c = native_source_case(tmp_path / "source", site)
    data, progress, controls, operation = c.data, c.progress, c.controls, c.operation
    parts, bindings, source = c.parts, c.bindings, c.source
    original, native_review, source_authority = (
        c.authority,
        c.native_review,
        c.source_authority,
    )
    observations, retrieval = c.observations, c.retrieval
    allowed = AllowedTeacherEvidence.model_validate_json(
        data.store.read(source.source.allowed_input_ref)
    )
    body = native_evidence(allowed.messages[1].content)
    attempts = array_value(body["attempts"], "all four")
    assert len(attempts) == 4
    assert [object_value(a, "attempt")["candidate_slot"] for a in attempts] == [
        0,
        1,
        2,
        3,
    ]
    policy = teacher_projection_case(site).policy
    project, protection = build_teacher_context(policy)
    counter = UnitTeacherCounts(data.store)
    admission = teacher_source_authority(
        UnitAuthority(),
        source,
        evidence=data.store,
        observations=observations,
        retrieval=retrieval,
        authority=source_authority,
        operation=operation,
    )
    request = ContextPreparationRequest(
        schema_version="context-preparation-request/2",
        scope=source.source.scope,
        operation=operation,
        request_id=bindings.request_id,
        source=source.source,
        profile=profile(
            "teacher",
            context_window=400017,
            input_limit=400000,
            output_reserve=17,
            soft_target=340000,
        ),
        policy=policy,
    )
    prepared = prepare_context(
        request,
        ContextPreparationDeps(data.store, admission, project, protection, counter),
        control=controls.bind(operation),
    )
    assert prepared.outcome == "prepared" and counter.calls == 2
    shared = project.project(
        source.source, data.store.read(source.source.allowed_input_ref), policy
    )[1]
    messages = TeacherModelInput.model_validate_json(shared.input_bytes)
    assert "teacher-actor-visible-input/1" in messages.messages[0].content
    op = operation.cleanup(
        "native-source-closed-review", now=datetime.now(timezone.utc), seconds=60
    )
    recorded_authority = native_teacher_source_authority(
        original, tuple(parts), native_review, op
    )
    deps = TeacherSourceReviewDeps(
        data.store, observations, retrieval, recorded_authority, op
    )
    assert (
        review_teacher_source(source, deps, control=controls.bind(op)).source
        == source.source
    )
    closed_admission = teacher_source_authority(
        UnitAuthority(),
        source,
        evidence=data.store,
        observations=observations,
        retrieval=retrieval,
        authority=recorded_authority,
        operation=op,
    )
    final = review_context(
        request,
        prepared,
        ContextReviewDeps(
            data.store,
            closed_admission,
            project,
            protection,
            UnitTeacherCountReview(data.store),
        ),
        expected_input_ref=prepared.selected_input_ref,
        control=controls.bind(op),
    )
    assert final.outcome == "prepared" and counter.calls == 2
    # A known original unknown request still blocks a different Teacher ID.
    original.pending = True
    with pytest.raises(TeacherSourceUnconfirmed):
        publish_teacher_source(
            progress,
            bindings.model_copy(update={"request_id": "different-id"}),
            teacher_source_dependencies(
                data.store, observations, retrieval, recorded_authority
            ),
            control=controls.bind(operation),
        )


def test_original_actor_loop_once_native_count_send_then_teacher_projection_without_reexecution(
    tmp_path: Path,
) -> None:
    from actor_context_loop_fixtures import context_loop_case
    from lab_generate_skill.domain.teacher_attempt import (
        TeacherAttemptInput,
        TeacherFeedbackPolicy,
    )
    from lab_generate_skill.domain.teacher_scope import TeacherContextScope

    c = context_loop_case(tmp_path)
    c.base.loader.session.output = c.base.loader.session.output.model_copy(
        update={"text": '{"action":"send_msg_to_user(\'Done\')"}'}
    )
    snapshot = c.runner.run(c.request)
    trace = snapshot.project().sealed
    assert trace is not None and len(c.executions) == 1 and trace.interactions == 1
    store = c.base.loop.store
    controls = c.base.loop.journal.controls
    stop = ActorStop.model_validate_json(store.read(trace.stop_evidence_ref))
    feedback = Evaluation(
        identity=trace.scope.task,
        attempt_id=trace.scope.attempt_id,
        contract_ref=trace.stop_evidence_ref,
        evaluator_id="unit-loop-feedback",
        evaluator_version="1",
        status="failure",
        reward=0,
        checks=(
            CheckResult(
                name="original_goal",
                status="fail",
                reason_code="GOAL_MISMATCH",
                evidence=(trace.final_observation_ref,),
            ),
        ),
        reason_code="GOAL_MISMATCH",
    )
    auth = store.put(
        b'{"unit_only":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-feedback-authorization/1",
            visibility="private",
            producer="unit-no-real-permission",
        ),
    )
    operation = command("original-loop-teacher-source")
    original = TeacherAttemptInput(
        scope=TeacherContextScope(
            owner=trace.scope.owner,
            task=trace.scope.task,
            context_id=trace.scope.context_id,
        ),
        candidate_slot=0,
        actor_request_ref=stop.request_ref,
        trace_ref=put(store, trace),
        evaluation_ref=put(store, feedback),
        feedback=TeacherFeedbackPolicy(
            policy_id="unit-loop",
            authorization_ref=auth,
            check_names=("original_goal",),
        ),
        operation=operation,
    )
    observations = EvidenceObservations(store, controls)
    traces = EvidenceTraceRecords(store, controls, UnitTraceAuthority())
    authority = UnitNativeAuthority()
    published = publish_teacher_attempt(
        original,
        native_teacher_attempt(store, observations, traces, authority),
        control=controls.bind(operation),
    )
    before = c.base.loader.session.calls
    c.base.client.close(
        controls.bind(command("close-original-native-worker", attempt="attempt"))
    )
    sent = len(c.base.channel.sent)
    op = operation.cleanup(
        "native-after-worker-close", now=datetime.now(timezone.utc), seconds=60
    )
    review_teacher_attempt(
        published,
        native_teacher_attempt_review(store, observations, traces, authority),
        op,
        control=controls.bind(op),
    )
    native = TeacherAttemptView.model_validate_json(
        store.read(published.source.allowed_view_ref)
    )
    assert (
        native.native["generation_rounds"] == 1
        and c.base.loader.session.calls == before == 1
        and len(c.base.channel.sent) == sent
    )
