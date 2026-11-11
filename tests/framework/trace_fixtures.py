"""Recorded synthetic browser/model facts, optionally in real CAS; no live authority."""

import json
from dataclasses import dataclass
from typing import Callable
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.actor_generation import ActorDecision, ActorGeneration
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.interaction import InteractionEvent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.trace import InteractionTrace, TraceTurn
from observation_fixtures import sample_observation
from retrieval_fixtures import reference
from state_contract_fixtures import scope
from test_run_journal import command


@dataclass
class TraceFixture:
    trace: InteractionTrace
    observations: tuple[Observation, ...]


def fixture(
    store: FileEvidenceStore | None = None,
    outcomes: tuple[str, ...] = ("invalid", "returned", "returned"),
    *,
    terminal: bool = True,
) -> TraceFixture:
    bound = scope()
    observed = [sample_observation(bound.task, bound.context_id, bound.attempt_id)]

    def put(value: object, schema: str, visibility: str = "private") -> EvidenceRef:
        return reference(value, schema, visibility, store)

    initial = current = put(observed[0], "observation/1", "public")
    turns: list[TraceTurn] = []
    for index, outcome in enumerate(outcomes):
        gid, rid = f"gen-{index}", f"request-{index}"
        action = BrowserAction(
            action_id=f"action-{index}",
            protocol_id="unit-browser-v1",
            name="click",
            payload="click('2')\n",
        )
        status = (
            "uncertain"
            if outcome == "generation_unknown"
            else "failed" if outcome == "failed" else "completed"
        )
        generation = ActorGeneration.model_validate(
            dict(
                scope=bound,
                operation=command(gid, attempt=bound.attempt_id),
                generation_id=gid,
                request_id=rid,
                before_observation_ref=current,
                input_ref=put(
                    {"request_id": rid, "before": current.model_dump(mode="json")},
                    "actor-model-input/1",
                ),
                parameters_ref=put({"temperature": 0}, "model-parameters/1"),
                status=status,
                response_ref=(
                    put(
                        {
                            "generation_id": gid,
                            "action": (
                                None
                                if outcome in ("invalid", "unprocessed")
                                else action.model_dump(mode="json")
                            ),
                        },
                        "actor-model-response/1",
                    )
                    if status == "completed"
                    else None
                ),
                failure_ref=(
                    None
                    if status == "completed"
                    else put({"status": status}, "generation-failure/1")
                ),
            )
        )
        decision = None
        event = None
        if status == "completed" and outcome != "unprocessed":
            if outcome == "invalid":
                decision = ActorDecision(
                    generation_id=gid,
                    outcome="invalid",
                    failure_ref=put({"error": "parse"}, "actor-parse-failure/1"),
                )
            else:
                decision = ActorDecision(
                    generation_id=gid, outcome="action", action=action
                )
                result = None
                step_op = command(f"step-{index}", attempt=bound.attempt_id)
                if outcome == "returned":
                    observed.append(
                        observed[-1].model_copy(
                            update={
                                "observation_id": f"observed-{index}",
                                "sequence": len(observed),
                                "text": f"returned {index}",
                            }
                        )
                    )
                    after = put(observed[-1], "observation/1", "public")
                    ended = terminal and index == len(outcomes) - 1
                    result = StepResult(
                        scope=bound,
                        operation=step_op,
                        action_id=action.action_id,
                        before_observation_ref=current,
                        observation_ref=after,
                        return_ref=put(
                            {
                                "action_id": action.action_id,
                                "observation_ref": after.model_dump(mode="json"),
                                "terminal": ended,
                            },
                            "browser-step-return/1",
                        ),
                        terminal=ended,
                    )
                event = InteractionEvent.model_validate(
                    dict(
                        scope=bound,
                        operation=step_op,
                        generation_id=gid,
                        action=action,
                        before_observation_ref=current,
                        outcome=outcome,
                        result=result,
                        failure_ref=(
                            None
                            if result
                            else put({"outcome": outcome}, "interaction-failure/1")
                        ),
                    )
                )
                if result:
                    current = result.observation_ref
        turns.append(
            TraceTurn(generation=generation, decision=decision, interaction=event)
        )
    stop = "error"
    if outcomes and outcomes[-1] in ("generation_unknown", "uncertain"):
        stop = "uncertain"
    elif (
        turns
        and turns[-1].interaction
        and turns[-1].interaction.result
        and turns[-1].interaction.result.terminal
    ):
        stop = "finished"
    trace = InteractionTrace.model_validate(
        dict(
            scope=bound,
            operation=command("trace-seal", attempt=bound.attempt_id),
            initial_observation_ref=initial,
            max_generations=10,
            max_interactions=10,
            turns=tuple(turns),
            stop_reason=stop,
            stop_evidence_ref=put({"reason": stop}, "trace-stop/1"),
        )
    )
    return TraceFixture(trace, tuple(observed))


class UnitTraceAuthority:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.calls = 0
        self.denied = False
        self.callback: Callable[[], None] | None = None

    def verify(
        self,
        trace: InteractionTrace,
        observations: tuple[ResolvedObservation, ...],
        op: OperationContext,
    ) -> None:
        self.calls += 1
        if self.denied:
            raise OwnershipConflict("Unit trace authority denied")
        for turn in trace.turns:
            gen = turn.generation
            if json.loads(self.store.read(gen.input_ref)) != {
                "request_id": gen.request_id,
                "before": gen.before_observation_ref.model_dump(mode="json"),
            }:
                raise OwnershipConflict("Unit actual model input changed")
            if gen.response_ref is not None:
                expected = (
                    turn.decision.action.model_dump(mode="json")
                    if turn.decision and turn.decision.action
                    else None
                )
                if json.loads(self.store.read(gen.response_ref)) != {
                    "generation_id": gen.generation_id,
                    "action": expected,
                }:
                    raise OwnershipConflict("Unit actual model response changed")
            event = turn.interaction
            if event and event.result:
                result = event.result
                if json.loads(self.store.read(result.return_ref)) != {
                    "action_id": result.action_id,
                    "observation_ref": result.observation_ref.model_dump(mode="json"),
                    "terminal": result.terminal,
                }:
                    raise OwnershipConflict("Unit actual browser return changed")
        if self.callback:
            self.callback()
