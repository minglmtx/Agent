"""One typed synthetic model/browser return, never an actual dispatch receipt."""

from datetime import datetime, timezone
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata, Visibility
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_action_protocol import PROTOCOL
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.actor_generation import ActorGeneration, ActorDecision
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.trace import InteractionTrace, TraceTurn
from lab_generate_skill.domain.observation import Observation
from evidence_control_fixtures import EvidenceFixtureStore
from observation_fixtures import sample_observation
from test_slurm_commands import guard


def one_return(
    store: EvidenceFixtureStore,
    task: PublicTask,
    scope: StateScope,
    browser_operation: OperationContext,
    *,
    initial_ref: EvidenceRef | None = None,
) -> InteractionTrace:
    def raw(
        data: bytes, schema: str, visibility: Visibility = "private"
    ) -> EvidenceRef:
        return store.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility=visibility,
                producer="explicit-synthetic-trace",
            ),
            guard(),
        )

    def put(value: Contract, visibility: Visibility = "private") -> EvidenceRef:
        return raw(
            value.model_dump_json().encode(),
            str(value.model_dump()["schema_version"]),
            visibility,
        )

    if initial_ref is None:
        initial = sample_observation(task.identity, scope.context_id, scope.attempt_id)
        initial = initial.model_copy(
            update={
                "tabs": tuple(
                    t.model_copy(update={"url": task.start_url}) for t in initial.tabs
                ),
                "captured_at": datetime.now(timezone.utc),
            }
        )
        initial_ref = put(initial, "public")
    else:
        initial = Observation.model_validate_json(store.read(initial_ref, guard()))
        assert (
            initial.task,
            initial.context_id,
            initial.attempt_id,
            initial.sequence,
        ) == (task.identity, scope.context_id, scope.attempt_id, 0)
    action = BrowserAction(
        action_id="synthetic-click",
        protocol_id=PROTOCOL,
        name="click",
        payload="click('2')",
    )
    operation = browser_operation.model_copy(update={"operation_id": "synthetic-click"})
    observed = initial.model_copy(
        update={
            "observation_id": "after-synthetic-click",
            "sequence": 1,
            "captured_at": datetime.now(timezone.utc),
        }
    )
    observed_ref = put(observed, "public")
    returned = BrowserReadout(
        schema_version="browser-step-return/1",
        scope=scope,
        operation=operation,
        action=action,
        observation=observed,
        events=(),
        environment_reward=0.0,
        terminated=False,
        truncated=False,
        protocol_terminal=False,
    )
    result = StepResult(
        scope=scope,
        operation=operation,
        action_id=action.action_id,
        before_observation_ref=initial_ref,
        observation_ref=observed_ref,
        return_ref=put(returned),
        terminal=False,
    )
    generation = ActorGeneration(
        scope=scope,
        operation=browser_operation.model_copy(
            update={"operation_id": "synthetic-generation"}
        ),
        generation_id="synthetic-generation",
        request_id="synthetic-request",
        before_observation_ref=initial_ref,
        input_ref=raw(b"{}", "actor-model-input/1"),
        parameters_ref=raw(b"{}", "model-parameters/1"),
        status="completed",
        response_ref=raw(b"{}", "actor-model-response/1"),
        failure_ref=None,
    )
    event = InteractionEvent(
        scope=scope,
        operation=operation,
        generation_id=generation.generation_id,
        action=action,
        before_observation_ref=initial_ref,
        outcome="returned",
        result=result,
    )
    return InteractionTrace(
        scope=scope,
        operation=browser_operation.model_copy(
            update={"operation_id": "synthetic-seal"}
        ),
        initial_observation_ref=initial_ref,
        max_generations=1,
        max_interactions=1,
        turns=(
            TraceTurn(
                generation=generation,
                decision=ActorDecision(
                    generation_id=generation.generation_id,
                    outcome="action",
                    action=action,
                ),
                interaction=event,
            ),
        ),
        stop_reason="interaction_limit",
        stop_evidence_ref=raw(b'{"explicitly_synthetic":true}', "trace-stop/1"),
    )
