"""Frozen Actor process specification; admission is supplied by an authority."""

from lab_generate_skill.domain.causal_model import validate_causal_artifact

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .lifecycle import AllocationToken
from .release import ReleaseArtifact
from .actor_engine import ActorEngineConfig
from .actor_step import ActorSlurmBinding


class ActorResourceSpec(Contract):
    schema_version: Literal["actor-resource-spec/1"] = "actor-resource-spec/1"
    token: AllocationToken
    release_ref: EvidenceRef
    model_binding_ref: EvidenceRef
    python_executable: str = Field(min_length=1, max_length=4096)
    slurm: ActorSlurmBinding
    artifact: ReleaseArtifact
    engine_config: ActorEngineConfig

    @model_validator(mode="after")
    def bindings(self) -> Self:
        path = PurePosixPath(self.python_executable)
        if (
            not path.is_absolute()
            or str(path) != self.python_executable
            or ".." in path.parts
            or "\0" in self.python_executable
        ):
            raise ValueError("Actor needs a canonical absolute executable path")
        if (
            self.token.scope != "batch"
            or self.token.resource_kind != "actor"
            or self.token.provider_id != "fixed-actor-worker"
            or self.token.provider_version != "1"
        ):
            raise ValueError("Actor requires its explicit batch provider binding")
        if (
            self.release_ref.visibility != "private"
            or self.release_ref.content_schema != "release-manifest/1"
        ):
            raise ValueError("Actor requires private frozen release reference")
        if (
            self.model_binding_ref.visibility,
            self.model_binding_ref.content_schema,
        ) != ("private", "model-binding/1"):
            raise ValueError("Actor requires its exact private model binding")
        if self.token.owner.job_id != self.slurm.allocation.facts.execution.job_id:
            raise ValueError("Actor owner differs from the original Slurm execution")
        validate_causal_artifact(self.artifact)
        return self
