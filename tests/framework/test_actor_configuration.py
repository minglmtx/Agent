"""Owner-free configuration checks; synthetic declarations, no CAS or resources."""

from dataclasses import dataclass, replace
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.context_tokens import actor_budget_profile
from lab_generate_skill.domain.actor_configuration import (
    check_actor_model_configuration,
    check_actor_parameter_configuration,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from actor_long_fixtures import long_config


def ref(raw: bytes, schema: str) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="unit-pure-configuration",
        ),
    )


@dataclass(frozen=True)
class ConfigurationCase:
    artifact: ReleaseArtifact
    config: ActorEngineConfig
    binding: ActorModelBinding
    route: EvidenceRef
    parameters: LocalActorParameters
    parameters_ref: EvidenceRef

    def check(self) -> None:
        check_actor_model_configuration(
            self.artifact, self.config, self.binding, self.route
        )
        check_actor_parameter_configuration(
            self.config, self.parameters, self.parameters_ref
        )


@pytest.fixture
def c() -> ConfigurationCase:
    config = long_config()
    model = ReleaseArtifact(
        artifact_id="model",
        root="/unit-not-installed/model",
        files=(
            ReleaseFile(
                path="weights.safetensors",
                sha256="a" * 64,
                size_bytes=1,
                executable=False,
            ),
        ),
    )
    binding = ActorModelBinding(
        model="unit/pure-config",
        release_ref=ref(b"unit-declaration-only", "release-manifest/1"),
        component_id="actor",
        model_artifact_id=model.artifact_id,
        engine_config_artifact_id="engine-config",
        engine_config_ref=ref(config.model_dump_json().encode(), config.schema_version),
    )
    parameters = LocalActorParameters(
        max_input_tokens=61440,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
    )
    # No owner/token/source is invented. Release contents and files are not
    # verified here; the original release consumer still must verify them.
    return ConfigurationCase(
        model,
        config,
        binding,
        ref(binding.model_dump_json().encode(), "model-binding/1"),
        parameters,
        ref(parameters.model_dump_json().encode(), "model-parameters/1"),
    )


def test_repeatable_configuration_needs_no_store_or_resource(
    c: ConfigurationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins
    import os
    import subprocess

    before = repr(c)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Pure Actor configuration attempted I/O or resource acquisition")

    with monkeypatch.context() as patch:
        for module, name in [
            (builtins, "open"),
            (os, "open"),
            (os, "mkdir"),
            (subprocess, "Popen"),
        ]:
            patch.setattr(module, name, forbidden)
        for _ in range(2):
            c.check()
    assert repr(c) == before


@pytest.mark.parametrize(
    "change",
    [
        {"content_schema": "actor-model-binding/1"},
        {"visibility": "public"},
        {"media_type": "text/plain"},
        {"size_bytes": 1},
        {"sha256": "b" * 64, "uri": "cas://sha256/" + "b" * 64},
    ],
)
def test_model_envelope_must_match_body(
    c: ConfigurationCase, change: dict[str, Any]
) -> None:
    with pytest.raises((ValueError, OwnershipConflict)):
        replace(c, route=c.route.model_copy(update=change)).check()


@pytest.mark.parametrize(
    "change",
    [
        {"content_schema": "actor-engine-config/1"},
        {"size_bytes": 1},
        {"sha256": "b" * 64, "uri": "cas://sha256/" + "b" * 64},
        {"visibility": "public"},
        {"media_type": "text/plain"},
    ],
)
def test_config_bytes_and_schema_are_checked_by_original_profile_consumer(
    c: ConfigurationCase, change: dict[str, Any]
) -> None:
    binding = c.binding.model_copy(
        update={
            "engine_config_ref": c.binding.engine_config_ref.model_copy(update=change)
        }
    )
    route = ref(binding.model_dump_json().encode(), "model-binding/1")
    with pytest.raises((ValueError, OwnershipConflict)):
        actor_budget_profile(
            c.artifact,
            c.config,
            binding,
            route,
            c.parameters,
            c.parameters_ref,
            soft_target=24576,
        )


@pytest.mark.parametrize("value", [None, {}, (), "", 1])
def test_empty_wrong_typed_model_is_refused(c: ConfigurationCase, value: Any) -> None:
    with pytest.raises((TypeError, ValidationError)):
        check_actor_model_configuration(c.artifact, c.config, value, c.route)


@pytest.mark.parametrize(
    "change",
    [
        {"max_new_tokens": 3482},
        {"max_new_tokens": 4095},
        {"max_new_tokens": True},
        {"max_input_tokens": "61440"},
        {"max_input_tokens": 0},
        {"enable_thinking": True},
    ],
)
def test_illegal_parameters_rejected_before_any_effect(
    c: ConfigurationCase, change: dict[str, Any]
) -> None:
    parameters = c.parameters.model_copy(update=change)
    with pytest.raises((ValueError, OwnershipConflict)):
        check_actor_parameter_configuration(c.config, parameters, c.parameters_ref)


def test_parameter_reference_and_model_artifact_cannot_be_substituted(
    c: ConfigurationCase,
) -> None:
    with pytest.raises(OwnershipConflict):
        replace(
            c, parameters_ref=c.parameters_ref.model_copy(update={"size_bytes": 1})
        ).check()
    with pytest.raises(OwnershipConflict):
        replace(
            c, artifact=c.artifact.model_copy(update={"artifact_id": "different"})
        ).check()
