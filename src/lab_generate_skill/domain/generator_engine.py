"""Frozen local Qwen3 loader configuration; no imports of model libraries.

Sampling remains LocalGeneratorParameters. The complete model artifact includes
its tokenizer, chat template and generation_config; package pins and device/dtype
are part of the engine configuration, never inferred from a missing checkpoint.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .causal_model import ModelPackage


class GeneratorEngineConfig(Contract):
    schema_version: Literal["generator-engine-config/1"] = "generator-engine-config/1"
    model_type: Literal["qwen3"] = "qwen3"
    dtype: Literal["bfloat16", "float16", "float32"]
    device: Literal["cuda:0"] = "cuda:0"
    cpu_threads: int = Field(ge=1, le=64)
    context_window: int = Field(ge=1, le=1048576)
    packages: tuple[ModelPackage, ...]

    @model_validator(mode="after")
    def fixed_runtime(self) -> Self:
        if [p.name for p in self.packages] != [
            "accelerate",
            "safetensors",
            "tokenizers",
            "torch",
            "transformers",
        ]:
            raise ValueError(
                "Generator requires five explicit ordered package versions"
            )
        return self
