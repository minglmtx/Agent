"""Cheap native-GPU harness checks, without model files or CUDA import."""

from pathlib import Path
import pytest
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.adapters.models.causal_session import CausalOutput
from lab_generate_skill.adapters.models.transformers_actor_session import (
    TransformersActorSession,
)
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_engine_live import saved_turn, W
from generator_model_assets import pinned_causal_model, pinned_model
from test_slurm_commands import guard


def test_actual_saved_input_and_explicit_actor_inventory() -> None:
    original = saved_turn()
    prompt = prepare_actor(original)
    assert original.observation.text is not None
    assert original.observation.text in prompt.messages[1].content
    artifact, digest = pinned_causal_model(
        W, "models/Qwen2.5-7B-Instruct", "qwen25-original"
    )
    assert digest == "3580a3d3854f18cf4b2ce7548afb899d82d055872076b0e2f1c031c9d8923f22"
    assert (
        artifact.artifact_id == "qwen25-original"
        and Path(artifact.root).name == "Qwen2.5-7B-Instruct"
    )
    generator, generator_digest = pinned_model(W)
    assert (
        generator_digest
        == "b444ebf5b8f360facdcd7cdbbdb851e85b26f915665d8e1499060083d6f221d8"
    )
    assert generator.artifact_id == "qwen3-original"


def test_shared_output_is_wrapped_in_actor_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object.__new__(TransformersActorSession)
    parameters = LocalActorParameters(
        max_input_tokens=3, max_new_tokens=1, seed=0, temperature=0.0, top_p=0.95
    )
    control = guard()

    def infer(
        tokens: tuple[int, ...], params: object, supplied_control: OperationControl
    ) -> CausalOutput:
        assert (
            tokens == (1, 2, 3) and params is parameters and supplied_control is control
        )
        return CausalOutput(
            text="x", finish_reason="length", prompt_tokens=3, completion_tokens=1
        )

    monkeypatch.setattr(session, "_infer", infer)
    output = session.infer((1, 2, 3), parameters, control)
    assert output.schema_version == "actor-engine-output/1" and output.text == "x"
