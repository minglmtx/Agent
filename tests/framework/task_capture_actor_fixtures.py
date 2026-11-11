"""Original v2 context/Actor loop; explicit synthetic count/model/source rights."""

from pathlib import Path
import hashlib
import json
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.application.actor_context_preparation import (
    ControlledActorContext,
)
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    TokenMeasurement,
    CountedContextInput,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_loop_fixtures import RunAuthority
from evidence_control_fixtures import EvidenceFixtureStore
from map_task_preparation_port_fixtures import MapPreparationPortCase
from retrieval_fixtures import reference
from test_evidence_run_plans import persisted_plan, frozen_binding


def freeze_run(p: MapPreparationPortCase) -> TaskExecutionPlan:
    store, scope = p.original.resource.evidence, p.original.scope
    old = persisted_plan(store)
    run = RunPlan.model_validate(
        old.model_copy(
            update={
                "tasks": (old.tasks[0].model_copy(update={"identity": scope.task}),),
                "resources": old.resources.model_copy(
                    update={
                        "max_actor_generations_per_attempt": 1,
                        "max_interactions_per_attempt": 1,
                    }
                ),
            }
        )
    )
    bound = frozen_binding(store, run).model_copy(update={"owner": scope.owner})
    return p.plan.model_copy(
        update={
            "intent": p.plan.intent.model_copy(
                update={
                    "binding": p.plan.intent.binding.model_copy(
                        update={
                            "run": bound,
                            "claim_ref": reference(
                                {"explicit_synthetic_source_permission": True},
                                "source-claim/1",
                                store=store,
                            ),
                        }
                    )
                }
            )
        }
    )


class SyntheticActorCounts:
    """Counter contract exercise only; never tokenizer/provider qualification."""

    def __init__(self, store: EvidenceFixtureStore) -> None:
        self.store, self.calls = store, 0

    def measure(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        prompt = ActorPrompt.model_validate_json(self.store.read(input_ref, control))
        self.calls += 1
        tokens = len(prompt.input_bytes()) // 4 + 1  # Explicit simulated count.
        measurement = TokenMeasurement(
            role="actor",
            input_ref=input_ref,
            profile_sha256=profile.digest,
            policy_sha256=policy.digest,
            input_tokens=tokens,
            upper_bound_tokens=tokens,
            precision="exact",
            complete_request=True,
            elapsed_seconds=0.0,
        )
        proof = reference(
            {
                "unit_counter_only": True,
                "input": input_ref.sha256,
                "tokens": tokens,
                "profile": profile.digest,
                "policy": policy.digest,
            },
            "actor-context-count-execution/1",
            store=self.store,
        )
        return CountedContextInput(measurement=measurement, evidence_ref=proof)

    def verify(
        self,
        counted: CountedContextInput,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> TokenMeasurement:
        measurement = counted.measurement
        raw = self.store.read(measurement.input_ref, control)
        prompt = ActorPrompt.model_validate_json(raw)
        proof = json.loads(self.store.read(counted.evidence_ref, control))
        assert proof == dict(
            unit_counter_only=True,
            input=hashlib.sha256(raw).hexdigest(),
            tokens=len(prompt.input_bytes()) // 4 + 1,
            profile=profile.digest,
            policy=policy.digest,
        )
        assert measurement.input_tokens == proof["tokens"]
        return measurement


def controlled_context(
    request: ActorRunRequest, journal: FileTraceJournal, store: EvidenceFixtureStore
) -> ControlledActorContext:
    assert request.context_configuration_ref is not None
    cfg = ActorContextConfiguration.model_validate_json(
        store.read(request.context_configuration_ref)
    )
    project, protect = build_actor_context(cfg.policy)
    return ControlledActorContext(
        request,
        journal,
        store,
        EvidenceObservations(store, journal.controls),
        RunAuthority(),
        journal.controls,
        project,
        protect,
        SyntheticActorCounts(store),
    )
