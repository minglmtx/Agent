"""Exact native Actor counts bound to the complete immutable invocation.

These facts grant neither source admission nor permission to generate. File pin
identities are declarations; the original resident engine verifies actual files.
"""

import hashlib
import json
from typing import Literal, Any
from pydantic import Field, model_serializer, SerializerFunctionWrapHandler
from .actor_versions import actor_version_fields, actor_version_output
from .actor_prompt import ActorPrompt
from .actor_engine import ActorEngineConfig, LocalActorParameters
from .causal_model import validate_causal_artifact
from .release import ReleaseArtifact
from .validation import Contract, Sha256
from .context_budget import TokenMeasurement
from .evidence import EvidenceRef
from .process_guard import ProcessOwnerGuard
from .release_installation import InstalledReleaseSources
from .state_scope import private_state_ref
from pydantic import model_validator
from typing import Self


def digest(value: Contract) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


def tokenizer_identity(artifact: ReleaseArtifact) -> str:
    artifact = validate_causal_artifact(artifact)
    # Include every non-weight file, including optional tokenizer assets. The
    # whole artifact identity separately binds weights and the immutable root.
    pins = sorted(
        (f.path, f.sha256, f.size_bytes)
        for f in artifact.files
        if not f.path.endswith((".safetensors", ".safetensors.index.json"))
    )
    return hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()


def template_identity(artifact: ReleaseArtifact) -> str:
    artifact = validate_causal_artifact(artifact)
    pins = sorted(
        (f.path, f.sha256, f.size_bytes)
        for f in artifact.files
        if f.path == "tokenizer_config.json" or f.path.endswith(".jinja")
    )
    return hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()


class ActorTokenCount(Contract):
    schema_version: Literal["actor-token-count/1", "actor-token-count/2"] = (
        "actor-token-count/1"
    )
    input_sha256: Sha256
    model_input_sha256: Sha256
    parameters_sha256: Sha256
    artifact_sha256: Sha256
    engine_config_sha256: Sha256
    tokenizer_sha256: Sha256
    template_sha256: Sha256
    input_tokens: int = Field(ge=1, le=2147483647)
    context_window: int = Field(ge=1, le=1048576)
    observation_tokens: int | None = Field(default=None, ge=0, le=2147483647)
    observation_body_sha256: Sha256 | None = None
    observation_counting_method: (
        Literal["fixed-actor-text-no-special-tokens-v1"] | None
    ) = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "actor-token-count/1",
            (
                "observation_tokens",
                "observation_body_sha256",
                "observation_counting_method",
            ),
        )

    @model_validator(mode="after")
    def selected_body_count(self) -> Self:
        old = self.schema_version == "actor-token-count/1"
        names = (
            "observation_tokens",
            "observation_body_sha256",
            "observation_counting_method",
        )
        actor_version_fields(self, old, names, record_name="Actor count")
        if old == any(getattr(self, name) is not None for name in names):
            raise ValueError(
                "Only explicit Actor count v2 carries the complete local body count"
            )
        if not old and any(getattr(self, name) is None for name in names):
            raise ValueError(
                "Local body count requires its exact source digest and counting method"
            )
        return self

    def verify(
        self,
        prompt: ActorPrompt,
        parameters: LocalActorParameters,
        artifact: ReleaseArtifact,
        config: ActorEngineConfig,
    ) -> None:
        expected = dict(
            input_sha256=digest(prompt),
            model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
            parameters_sha256=digest(parameters),
            artifact_sha256=digest(artifact),
            engine_config_sha256=digest(config),
            tokenizer_sha256=tokenizer_identity(artifact),
            template_sha256=template_identity(artifact),
            context_window=config.context_window,
        )
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("Native Actor count differs from frozen invocation")
        view = prompt.observation_view
        local = view is not None and view.mode == "local"
        if local != (self.schema_version == "actor-token-count/2"):
            raise ValueError("Native count omitted or invented local body measurement")
        if (
            local
            and view is not None
            and self.observation_body_sha256 != view.body_sha256
        ):
            raise ValueError("Native local count changed actual observation body")


class ActorCountExecution(Contract):
    schema_version: Literal["actor-context-count-execution/1"] = (
        "actor-context-count-execution/1"
    )
    measurement: TokenMeasurement
    guard: ProcessOwnerGuard
    installed_sources: InstalledReleaseSources
    command_ref: EvidenceRef
    reply_ref: EvidenceRef

    @model_validator(mode="after")
    def actor_wire_facts(self) -> Self:
        if self.measurement.role != "actor":
            raise ValueError("Actor native evidence cannot certify a Teacher count")
        private_state_ref(self.command_ref, "actor-context-count-command/1")
        private_state_ref(self.reply_ref, "actor-context-count-reply/1")
        return self
