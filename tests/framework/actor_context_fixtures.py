"""Only synthetic model/tokenizer and declarations; no business source permit."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.models.context_tokens import (
    ActorContextTokenCounter,
    actor_budget_profile,
)
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.context_budget import ContextBudgetProfile
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_engine_fixtures import Loader
from actor_worker_fixtures import worker_case, UnitChannel
from context_budget_fixtures import selection
from evidence_control_fixtures import EvidenceFixtureStore


@dataclass
class CounterCase:
    counter: ActorContextTokenCounter
    profile: ContextBudgetProfile
    policy: ContextProjectionPolicy
    input_ref: EvidenceRef
    evidence: EvidenceFixtureStore
    loader: Loader
    control: OperationControl
    client: SupervisedActorEngine
    channel: UnitChannel
    binding: ActorModelBinding
    parameters: LocalActorParameters

    def put(self, raw: bytes, schema: str) -> EvidenceRef:
        return self.evidence.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-context-counter",
            ),
            self.control,
        )


def counter_case(root: Path, *, configure: bool = True) -> CounterCase:
    engine, loader, prompt, params, control, _, channel, client = worker_case(root)
    evidence_root = root / "context-evidence"
    evidence_root.mkdir()
    evidence = EvidenceFixtureStore(evidence_root)

    def put(raw: bytes, schema: str) -> EvidenceRef:
        return evidence.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-context-counter",
            ),
            control,
        )

    # Synthetic references bind bytes but do not stand in for release validation.
    binding = ActorModelBinding(
        model="unit/qwen2",
        release_ref=put(b"{}", "release-manifest/1"),
        component_id="actor",
        model_artifact_id=engine.artifact.artifact_id,
        engine_config_artifact_id="configuration",
        engine_config_ref=put(
            engine.config.model_dump_json().encode(), "actor-engine-config/1"
        ),
    )
    profile = actor_budget_profile(
        engine.artifact,
        engine.config,
        binding,
        put(binding.model_dump_json().encode(), "model-binding/1"),
        params,
        put(params.model_dump_json().encode(), "model-parameters/1"),
        soft_target=80,
    )
    if configure:
        client.configure(control)
    counter = ActorContextTokenCounter(
        client, evidence, profile, binding, params, session_id="session"
    )
    return CounterCase(
        counter,
        profile,
        selection().policy,
        put(prompt.model_dump_json().encode(), "actor-model-input/1"),
        evidence,
        loader,
        control,
        client,
        channel,
        binding,
        params,
    )
