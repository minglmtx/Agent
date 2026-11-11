"""Canonical synthetic original Actor leaves, explicit unit source authority.

No source claim, site, model, resource or provider dispatch is qualified. Unlike
old approved-part markers, requests/completions/readouts here are actual schemas;
only the original loop combination test uses RecordedActorRunner itself.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone
import hashlib
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.bootstrap.teacher_attempt import (
    native_teacher_attempt,
    native_teacher_attempt_review,
)
from lab_generate_skill.domain.teacher_attempt import (
    TeacherAttemptInput,
    TeacherFeedbackPolicy,
)
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.actor_run import ActorRunRequest, ActorStop
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.actor_response import (
    ActorTextCompletion,
    ActorParseFailure,
)
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import (
    BrowserReadout,
    BrowserRuntimeEvent,
)
from lab_generate_skill.domain.evaluation import Evaluation, CheckResult
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.trace import InteractionTrace, TraceTurn
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.application.teacher_attempt import TeacherAttemptDeps
from lab_generate_skill.application.teacher_attempt_review import (
    TeacherAttemptReviewDeps,
)
from lab_generate_skill.actor.prompting import prepare_actor
from evidence_control_fixtures import EvidenceFixtureStore
from state_contract_fixtures import scope, allocation
from observation_fixtures import sample_observation
from test_actor_protocol import turn
from test_run_journal import command, CancelSwitch


class UnitNativeAuthority:
    denied = False
    calls = 0

    def verify_allowed(
        self,
        original: TeacherAttemptInput,
        request: ActorRunRequest,
        trace: InteractionTrace,
        evaluation: Evaluation,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise PermissionError("Original unit source permission denied")
        assert (
            request.scope == trace.scope
            and evaluation.attempt_id == trace.scope.attempt_id
        )


class UnitTraceAuthority:
    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None:
        assert trace.scope.owner.run_id == op.run_id
        assert observations[0].record.sequence == 0


@dataclass(frozen=True)
class NativeAttemptCase:
    root: Path
    store: EvidenceFixtureStore
    controls: OperationGuards
    original: TeacherAttemptInput
    request: ActorRunRequest
    trace: InteractionTrace
    evaluation: Evaluation
    deps: TeacherAttemptDeps
    review: TeacherAttemptReviewDeps
    authority: UnitNativeAuthority


def put(
    store: EvidenceFixtureStore,
    value: Contract,
    visibility: Literal["private", "public", "teacher"] = "private",
) -> EvidenceRef:
    schema = value.model_dump(mode="json")["schema_version"]
    assert type(schema) is str
    return store.put(
        value.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility=visibility,
            producer="unit-native-teacher-source",
        ),
    )


def native_attempt_case(
    root: Path,
    site: Site = "map",
    *,
    original_scope: StateScope | None = None,
    task: PublicTask | None = None,
    skill: CompactSkill | None = None,
    candidate_slot: int = 0,
    outcomes: tuple[str, ...] = ("invalid", "returned"),
    evaluation_status: Literal["success", "failure", "unknown"] = "failure",
    source_operation: OperationContext | None = None,
    request_v2: bool = False,
    shared_store: EvidenceFixtureStore | None = None,
) -> NativeAttemptCase:
    root.mkdir()
    if shared_store is None:
        (root / "evidence").mkdir()
        store = EvidenceFixtureStore(root / "evidence")
    else:
        store = shared_store
    public = turn()
    task = task or public.task.model_copy(
        update={"identity": public.task.identity.model_copy(update={"site": site})}
    )
    bound = original_scope or scope().model_copy(update={"task": task.identity})
    assert bound.task == task.identity

    def op(name: str, *, attempt: bool = True) -> OperationContext:
        return command(name, attempt=bound.attempt_id if attempt else None).model_copy(
            update={"run_id": bound.owner.run_id, "owner_id": bound.owner.owner_id}
        )

    observed = sample_observation(task.identity, bound.context_id, bound.attempt_id)
    initial = current = put(store, observed, "public")
    parameters = store.put(
        b'{"unit_original_parameters":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="model-parameters/1",
            visibility="private",
            producer="unit-native-teacher-source",
        ),
    )
    count = max(len(outcomes), 1)
    request = ActorRunRequest(
        scope=bound,
        task=task,
        skill=skill or public.skill,
        memory=public.memory,
        initial_observation_ref=initial,
        model_allocation=allocation("actor", attempt=False).model_copy(
            update={"owner": bound.owner}
        ),
        browser_allocation=allocation("browser").model_copy(
            update={"owner": bound.owner, "attempt_id": bound.attempt_id}
        ),
        parameters_refs=(parameters,) * count,
        operation=op("original-actor"),
        generation_seconds=10,
        interaction_seconds=10,
        cleanup_seconds=10,
    )
    preparation = None
    if request_v2:
        preparation = store.put(
            b'{"unit_preparation_marker":true}',
            EvidenceMetadata(
                media_type="application/json",
                content_schema="context-preparation/2",
                visibility="private",
                producer="unit-no-real-context-qualification",
            ),
        )
        request = ActorRunRequest.model_validate(
            {
                **request.model_dump(),
                "schema_version": "actor-run-request/2",
                "candidate_id": "native-original-candidate",
                "revision_round": max(0, candidate_slot - 3),
                "context_configuration_ref": store.put(
                    b'{"unit_configuration_marker":true}',
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="actor-context-configuration/1",
                        visibility="private",
                        producer="unit-no-real-context-qualification",
                    ),
                ),
            }
        )
    request_ref = put(store, request)
    turns = []
    stop: Literal["error", "finished", "uncertain"] = "error"
    for index, outcome in enumerate(outcomes):
        gid = f"g-{index}"
        rid = f"r-{index}"
        generation_op = op("model-" + str(index))
        prompt = prepare_actor(
            ActorPublicTurn(
                task=task,
                skill=request.skill,
                memory=request.memory,
                observation=ResolvedObservation(record=observed, text=observed.text),
                history=(),
            )
        )
        input_ref = put(store, prompt)
        completed = outcome not in ("model_unknown", "model_failed")
        completion = None
        if completed:
            completion = ActorTextCompletion(
                generation_id=gid,
                request_id=rid,
                input_ref=input_ref,
                model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
                parameters_ref=parameters,
                text=(
                    "complete original invalid proposal"
                    if outcome == "invalid"
                    else '{"action":"click(\'2\')"}'
                ),
                finish_reason="stop",
            )
        failure = (
            store.put(
                b'{"private_error":"WITHHELD_PRIVATE_DIAGNOSTIC"}',
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="generation-failure/1",
                    visibility="private",
                    producer="unit-native-teacher-source",
                ),
            )
            if not completed
            else None
        )
        generation = ActorGeneration.model_validate(
            dict(
                schema_version=(
                    "actor-generation/2" if request_v2 else "actor-generation/1"
                ),
                **({"context_preparation_ref": preparation} if request_v2 else {}),
                scope=bound,
                operation=generation_op,
                generation_id=gid,
                request_id=rid,
                before_observation_ref=current,
                input_ref=input_ref,
                parameters_ref=parameters,
                status=(
                    "completed"
                    if completed
                    else "failed" if outcome == "model_failed" else "uncertain"
                ),
                response_ref=None if completion is None else put(store, completion),
                failure_ref=failure,
            )
        )
        decision = None
        event = None
        if outcome == "invalid":
            assert generation.response_ref is not None
            parse = ActorParseFailure(
                generation_id=gid,
                response_ref=generation.response_ref,
                error_type="ValueError",
                message="original invalid public action syntax",
            )
            decision = ActorDecision(
                generation_id=gid, outcome="invalid", failure_ref=put(store, parse)
            )
        elif completed:
            action = BrowserAction(
                action_id="a-" + str(index),
                protocol_id="unit-browser-v1",
                name="click",
                payload="click('2')",
            )
            decision = ActorDecision(generation_id=gid, outcome="action", action=action)
            result = None
            event_failure = None
            event_op = op("browser-" + str(index))
            if outcome == "returned":
                after = observed.model_copy(
                    update={
                        "observation_id": "after-" + str(index),
                        "sequence": observed.sequence + 1,
                        "text": f"[1] heading 'original page {index}'\n[2] button 'Save' disabled value='€12.30'\n",
                        "last_action_error": "original rejected unsaved control",
                    }
                )
                terminal = index == len(outcomes) - 1
                returned = BrowserReadout(
                    scope=bound,
                    operation=event_op,
                    action=action,
                    observation=after,
                    events=(
                        BrowserRuntimeEvent(
                            sequence=0,
                            kind="after_action",
                            action_id=action.action_id,
                            status=200,
                        ),
                    ),
                    environment_reward=0.0,
                    terminated=False,
                    truncated=False,
                    protocol_terminal=terminal,
                )
                after_ref = put(store, after, "public")
                result = StepResult(
                    scope=bound,
                    operation=event_op,
                    action_id=action.action_id,
                    before_observation_ref=current,
                    observation_ref=after_ref,
                    return_ref=put(store, returned),
                    terminal=terminal,
                )
                observed = after
                current = after_ref
                if terminal:
                    stop = "finished"
            else:
                event_failure = store.put(
                    b'{"private_error":"WITHHELD_PRIVATE_INTERACTION"}',
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="interaction-failure/1",
                        visibility="private",
                        producer="unit-native-teacher-source",
                    ),
                )
                if outcome == "uncertain":
                    stop = "uncertain"
            event = InteractionEvent.model_validate(
                dict(
                    scope=bound,
                    operation=event_op,
                    generation_id=gid,
                    action=action,
                    before_observation_ref=generation.before_observation_ref,
                    outcome=outcome,
                    result=result,
                    failure_ref=event_failure,
                )
            )
        else:
            stop = "error" if outcome == "model_failed" else "uncertain"
        turns.append(
            TraceTurn(generation=generation, decision=decision, interaction=event)
        )
    returns = sum(
        t.interaction is not None
        and t.interaction.outcome in ("returned", "returned_incomplete")
        for t in turns
    )
    stop_fact = ActorStop(
        request_ref=request_ref,
        scope=bound,
        reason=stop,
        generations=len(turns),
        interactions=returns,
        final_observation_ref=current,
    )
    trace = InteractionTrace(
        scope=bound,
        operation=op("original-trace"),
        initial_observation_ref=initial,
        max_generations=count,
        max_interactions=count,
        turns=tuple(turns),
        stop_reason=stop,
        stop_evidence_ref=put(store, stop_fact),
    )
    trace_ref = put(store, trace)
    secret = store.put(
        b"PRIVATE_REFERENCE_ANSWER_NOT_FOR_TEACHER",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="unit-hidden-answer/1",
            visibility="private",
            producer="unit-native-teacher-source",
        ),
    )
    evaluation = Evaluation(
        identity=task.identity,
        attempt_id=bound.attempt_id,
        contract_ref=secret,
        evaluator_id="unit-original-evaluator",
        evaluator_version="1",
        status=evaluation_status,
        reward=(
            None
            if evaluation_status == "unknown"
            else int(evaluation_status == "success")
        ),
        checks=(
            CheckResult(
                name="original_goal",
                status=(
                    "unknown"
                    if evaluation_status == "unknown"
                    else "pass" if evaluation_status == "success" else "fail"
                ),
                reason_code="PRIVATE_NOT_PROJECTED",
                evidence=() if evaluation_status == "unknown" else (secret,),
            ),
        ),
        reason_code="PRIVATE_NOT_PROJECTED",
        evidence=(secret,),
    )
    evaluation_ref = put(store, evaluation)
    auth_ref = store.put(
        b'{"unit_authorization_only":true}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-feedback-authorization/1",
            visibility="private",
            producer="unit-no-production-qualification",
        ),
    )
    source_op = source_operation or op("original-teacher-part", attempt=False)
    original = TeacherAttemptInput(
        scope=TeacherContextScope(
            owner=bound.owner, task=bound.task, context_id=bound.context_id
        ),
        candidate_slot=candidate_slot,
        actor_request_ref=request_ref,
        trace_ref=trace_ref,
        evaluation_ref=evaluation_ref,
        feedback=TeacherFeedbackPolicy(
            policy_id="unit-source-policy",
            authorization_ref=auth_ref,
            check_names=("original_goal",),
        ),
        operation=source_op,
    )
    controls = OperationGuards(SystemClock(), CancelSwitch())
    observations = EvidenceObservations(store, controls)
    traces = EvidenceTraceRecords(store, controls, UnitTraceAuthority())
    authority = UnitNativeAuthority()
    deps = native_teacher_attempt(store, observations, traces, authority)
    review = native_teacher_attempt_review(store, observations, traces, authority)
    return NativeAttemptCase(
        root,
        store,
        controls,
        original,
        request,
        trace,
        evaluation,
        deps,
        review,
        authority,
    )


def cleanup(c: NativeAttemptCase) -> OperationContext:
    return c.original.operation.cleanup(
        "native-readonly-after-close", now=datetime.now(timezone.utc), seconds=60
    )
