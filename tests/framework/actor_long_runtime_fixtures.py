"""Original model ports/frames with explicit synthetic long-tokenizer facts.

This fixture conveys no GPU, installed release, native source or request rights.
"""

from pathlib import Path
from lab_generate_skill.adapters.models.actor_service import ActorService
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.adapters.models.context_tokens import (
    ActorContextTokenCounter,
    actor_budget_profile,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from actor_context_fixtures import CounterCase
from actor_long_fixtures import long_config
from actor_engine_fixtures import setup
from actor_installation_fixtures import unit_declaration, unit_verifier
from actor_worker_fixtures import UnitChannel, unit_guard
from context_budget_fixtures import selection
from evidence_control_fixtures import EvidenceFixtureStore


def long_counter_case(root: Path) -> CounterCase:
    old, loader, prompt, _, control = setup(root)
    engine = ResidentActorEngine(old.artifact, long_config(), loader=loader)
    service = ActorService(lambda artifact, config: engine, unit_verifier, unit_guard)
    channel = UnitChannel(service)
    client = SupervisedActorEngine(
        channel, "session", engine.artifact, engine.config, unit_declaration()
    )
    evidence_root = root / "long-context-evidence"
    evidence_root.mkdir()
    evidence = EvidenceFixtureStore(evidence_root)

    def put(raw: bytes, schema: str) -> EvidenceRef:
        return evidence.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-long-context-counter",
            ),
            control,
        )

    parameters = LocalActorParameters(
        max_input_tokens=61440,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
        enable_thinking=False,
    )
    binding = ActorModelBinding(
        model="unit/qwen2-long",
        release_ref=put(b"{}", "release-manifest/1"),
        component_id="actor",
        model_artifact_id=engine.artifact.artifact_id,
        engine_config_artifact_id="configuration",
        engine_config_ref=put(
            engine.config.model_dump_json().encode(), engine.config.schema_version
        ),
    )
    profile = actor_budget_profile(
        engine.artifact,
        engine.config,
        binding,
        put(binding.model_dump_json().encode(), "model-binding/1"),
        parameters,
        put(parameters.model_dump_json().encode(), "model-parameters/1"),
        soft_target=24576,
    )
    client.configure(control)
    counter = ActorContextTokenCounter(
        client, evidence, profile, binding, parameters, session_id="session"
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
        parameters,
    )
