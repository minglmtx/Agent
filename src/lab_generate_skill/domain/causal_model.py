"""Shared immutable model-file and dependency-pin rules; no role admission."""

from typing import Literal
from .release import ReleaseArtifact
from .validation import Contract, NonEmptyText


class ModelPackage(Contract):
    name: Literal["accelerate", "safetensors", "tokenizers", "torch", "transformers"]
    version: NonEmptyText


def validate_causal_artifact(artifact: ReleaseArtifact) -> ReleaseArtifact:
    artifact = ReleaseArtifact.model_validate(artifact)
    names = {f.path for f in artifact.files}
    if (
        not {
            "config.json",
            "generation_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
        }
        <= names
    ):
        raise ValueError(
            "Causal model artifact lacks model/tokenizer/generation configuration"
        )
    if "model.safetensors" not in names and "model.safetensors.index.json" not in names:
        raise ValueError("Causal model artifact needs explicit safetensors weights")
    if any(name.endswith(".py") or name.endswith(".bin") for name in names):
        raise ValueError(
            "Causal model artifact cannot supply Python code or pickle weights"
        )
    return artifact
