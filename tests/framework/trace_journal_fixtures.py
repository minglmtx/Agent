"""Real run plans/CAS/journals and synthetic model/browser facts, no live permission."""

import json
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution import AttemptBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.trace_events import (
    ActionPlanned,
    DecisionRejected,
    GenerationIntent,
    GenerationObserved,
    GenerationPlanned,
    InteractionObserved,
    TraceProgressEvent,
    TraceSealed,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.trace_plan import TraceCapacity, TracePlan
from lab_generate_skill.runtime.lifecycle import OperationGuards
from retrieval_fixtures import reference
from test_evidence_run_plans import persisted_plan, frozen_binding
from test_run_journal import command, CancelSwitch
from trace_fixtures import fixture as trace_fixture, TraceFixture, UnitTraceAuthority


class UnitLiveTraceAuthority(UnitTraceAuthority):
    def verify_plan(self, plan: TracePlan, op: OperationContext) -> None:
        if self.denied or json.loads(self.store.read(plan.binding.claim_ref)) != {
            "trace_claim": True
        }:
            raise OwnershipConflict("Unit trace plan permission denied")

    def verify_event(
        self, snapshot: TraceSnapshot, event: TraceProgressEvent, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("Unit live trace event denied")
        if isinstance(event, GenerationObserved):
            gen = event.generation
            if json.loads(self.store.read(gen.input_ref)) != {
                "request_id": gen.request_id,
                "before": gen.before_observation_ref.model_dump(mode="json"),
            }:
                raise OwnershipConflict("Unit original generation input changed")
            if (
                gen.response_ref is not None
                and json.loads(self.store.read(gen.response_ref))["generation_id"]
                != gen.generation_id
            ):
                raise OwnershipConflict("Unit generation response identity changed")
        if isinstance(event, (ActionPlanned, DecisionRejected)):
            pending_generation = snapshot.project().generation
            assert pending_generation and pending_generation.response_ref
            action = (
                event.decision.action.model_dump(mode="json")
                if event.decision.action
                else None
            )
            if json.loads(self.store.read(pending_generation.response_ref)) != {
                "generation_id": pending_generation.generation_id,
                "action": action,
            }:
                raise OwnershipConflict(
                    "Unit parsed decision changed actual model response"
                )
        if (
            isinstance(event, InteractionObserved)
            and event.interaction.result is not None
        ):
            result = event.interaction.result
            if json.loads(self.store.read(result.return_ref)) != {
                "action_id": result.action_id,
                "observation_ref": result.observation_ref.model_dump(mode="json"),
                "terminal": result.terminal,
            }:
                raise OwnershipConflict("Unit actual return changed")


@dataclass
class LiveTraceFixture:
    root: Path
    store: FileEvidenceStore
    plan: TracePlan
    data: TraceFixture
    authority: UnitLiveTraceAuthority

    def journal(self) -> FileTraceJournal:
        return FileTraceJournal(
            self.root / "journal",
            self.plan,
            OperationGuards(SystemClock(), CancelSwitch()),
            self.store,
            self.authority,
        )

    def events(self) -> tuple[TraceProgressEvent, ...]:
        events: list[TraceProgressEvent] = []
        for turn in self.data.trace.turns:
            gen = turn.generation
            fields = gen.model_dump(exclude={"schema_version"})
            intent = GenerationIntent.model_validate(
                {
                    "schema_version": (
                        "actor-generation-intent/2"
                        if gen.schema_version == "actor-generation/2"
                        else "actor-generation-intent/1"
                    ),
                    **{
                        key: value
                        for key, value in fields.items()
                        if key in GenerationIntent.model_fields
                    },
                }
            )
            events.append(
                GenerationPlanned(
                    operation=command(
                        "record-intent-" + gen.generation_id, attempt="attempt"
                    ),
                    intent=intent,
                )
            )
            events.append(
                GenerationObserved(
                    operation=command(
                        "record-response-" + gen.generation_id, attempt="attempt"
                    ),
                    generation=gen,
                )
            )
            if turn.decision is not None:
                if turn.decision.outcome == "invalid":
                    events.append(
                        DecisionRejected(
                            operation=command(
                                "record-decision-" + gen.generation_id,
                                attempt="attempt",
                            ),
                            decision=turn.decision,
                        )
                    )
                else:
                    assert turn.interaction is not None
                    events.append(
                        ActionPlanned(
                            operation=command(
                                "record-action-" + gen.generation_id, attempt="attempt"
                            ),
                            decision=turn.decision,
                            execution_operation=turn.interaction.operation,
                        )
                    )
                    events.append(
                        InteractionObserved(
                            operation=command(
                                "record-return-" + gen.generation_id, attempt="attempt"
                            ),
                            interaction=turn.interaction,
                        )
                    )
        trace = self.data.trace
        events.append(
            TraceSealed(
                operation=trace.operation,
                stop_reason=trace.stop_reason,
                stop_evidence_ref=trace.stop_evidence_ref,
            )
        )
        return tuple(events)


def fixture(
    root: Path,
    *,
    capacity: TraceCapacity | None = None,
    outcomes: tuple[str, ...] = ("invalid", "returned", "returned"),
) -> LiveTraceFixture:
    (root / "evidence").mkdir()
    (root / "journal").mkdir()
    store = FileEvidenceStore(root / "evidence")
    data = trace_fixture(store, outcomes)
    run = persisted_plan(store)
    run = RunPlan.model_validate(
        run.model_copy(
            update={
                "tasks": (
                    run.tasks[0].model_copy(update={"identity": data.trace.scope.task}),
                )
            }
        )
    )
    bound = frozen_binding(store, run).model_copy(
        update={"owner": data.trace.scope.owner}
    )
    plan = TracePlan(
        binding=AttemptBinding(
            run=bound,
            task=data.trace.scope.task,
            attempt_id="attempt",
            claim_ref=reference({"trace_claim": True}, store=store),
        ),
        scope=data.trace.scope,
        initial_observation_ref=data.trace.initial_observation_ref,
        max_generations=run.resources.max_actor_generations_per_attempt,
        max_interactions=run.resources.max_interactions_per_attempt,
        capacity=capacity
        or TraceCapacity(
            max_events=128,
            max_bytes=1024 * 1024,
            max_event_bytes=32768,
            max_trace_bytes=1024 * 1024,
        ),
    )
    data.trace = data.trace.model_copy(
        update={
            "max_generations": plan.max_generations,
            "max_interactions": plan.max_interactions,
        }
    )
    return LiveTraceFixture(root, store, plan, data, UnitLiveTraceAuthority(store))
