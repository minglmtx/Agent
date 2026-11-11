"""Fixed local Qwen2.5 Actor engine and explicit sampling; no model import."""

from typing import Any, Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .causal_model import ModelPackage
from .actor_long_context import ActorLongContext
from .actor_versions import actor_version_fields, actor_version_output
from .validation import Contract, NonEmptyText


class ActorEngineConfig(Contract):
    schema_version: Literal["actor-engine-config/1", "actor-engine-config/2"] = (
        "actor-engine-config/1"
    )
    long_context: ActorLongContext | None = None
    model_type: Literal["qwen2"] = "qwen2"
    dtype: Literal["bfloat16", "float16", "float32"]
    device: Literal["cuda:0"] = "cuda:0"
    cpu_threads: int = Field(ge=1, le=64)
    context_window: int = Field(ge=1, le=1048576)
    packages: tuple[ModelPackage, ...]

    @model_serializer(mode="wrap")
    def wire_version(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "actor-engine-config/1",
            ("long_context",),
        )

    @model_validator(mode="after")
    def fixed_runtime(self) -> Self:
        old = self.schema_version == "actor-engine-config/1"
        actor_version_fields(self, old, ("long_context",), record_name="Actor engine")
        if old != (self.long_context is None):
            raise ValueError(
                "Actor engine v2 requires explicit long configuration; v1 forbids it"
            )
        if not old:
            assert self.long_context is not None
            if self.context_window not in (65536, 131072) or self.dtype != "bfloat16":
                raise ValueError(
                    "Long Actor requires explicit 64K/128K BF16 configuration"
                )
            if self.context_window == 131072 and self.long_context.gpu_class not in (
                "a100_40gb",
                "a100_80gb",
            ):
                raise ValueError(
                    "128K Actor is restricted to separately validated full A100 classes"
                )
        if [p.name for p in self.packages] != [
            "accelerate",
            "safetensors",
            "tokenizers",
            "torch",
            "transformers",
        ]:
            raise ValueError("Actor requires five explicit ordered package versions")
        return self

    def check_output_reserve(self, tokens: int) -> None:
        long = self.long_context
        if long is None:
            return
        if type(tokens) is not int or tokens < long.minimum_output_reserve:
            raise ValueError(
                "Actor output reserve is below the fixed original85% floor3482"
            )
        if tokens < long.baseline_output_reserve:
            raise ValueError(
                "Reduced Actor output profiles require independent completeness qualification; none enabled"
            )


class LocalActorParameters(Contract):
    schema_version: Literal["local-actor-parameters/1"] = "local-actor-parameters/1"
    max_input_tokens: int = Field(ge=1, le=1048576)
    max_new_tokens: int = Field(ge=1, le=65536)
    seed: int = Field(ge=0, le=2147483647)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(gt=0, le=1, allow_inf_nan=False)
    enable_thinking: bool = False

    @model_validator(mode="after")
    def selected_actor_mode(self) -> Self:
        if self.enable_thinking:
            raise ValueError("The selected Qwen2.5 Actor has no thinking mode")
        return self


class LocalActorOutput(Contract):
    schema_version: Literal["actor-engine-output/1"] = "actor-engine-output/1"
    text: str
    finish_reason: NonEmptyText
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
