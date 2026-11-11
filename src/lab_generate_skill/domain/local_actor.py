"""Original local Actor binding, consumed call identity and actual exchange fact."""

import hashlib
import json
from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract
from .lifecycle import AllocationToken
from .evidence import EvidenceRef
from .process_guard import ProcessOwnerGuard
from .trace_events import GenerationIntent
from .actor_engine import LocalActorOutput
from .actor_execution_window import ActorDispatchTiming
from .state_scope import private_state_ref


class LocalActorBinding(Contract):
    schema_version: Literal["local-actor-binding/1"] = "local-actor-binding/1"
    resource: AllocationToken
    release_ref: EvidenceRef
    model_binding_ref: EvidenceRef
    spec_ref: EvidenceRef
    acquired_ref: EvidenceRef
    cleanup_seconds: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def original_resource(self) -> Self:
        token = self.resource
        if (
            token.scope,
            token.resource_kind,
            token.provider_id,
            token.provider_version,
        ) != ("batch", "actor", "fixed-actor-worker", "1"):
            raise ValueError("Actor needs its original fixed batch resource")
        for ref, schema in (
            (self.release_ref, "release-manifest/1"),
            (self.model_binding_ref, "model-binding/1"),
            (self.spec_ref, "actor-resource-spec/1"),
            (self.acquired_ref, "actor-resource-fact/1"),
        ):
            private_state_ref(ref, schema)
        return self


class LocalActorCall(Contract):
    schema_version: Literal["local-actor-call/1"] = "local-actor-call/1"
    binding: LocalActorBinding
    intent: GenerationIntent

    @model_validator(mode="after")
    def same_owner(self) -> Self:
        token, intent = self.binding.resource, self.intent
        if intent.scope.owner != token.owner or (
            intent.operation.allocation_id,
            intent.operation.recovery_ref,
        ) != (token.allocation_id, token.recovery_ref):
            raise ValueError(
                "Actor call must retain original owner and model allocation"
            )
        return self

    @property
    def key(self) -> str:
        # Exclude allocation/release/attempt: changing them must not recreate
        # permission for the same original source request in this trusted root.
        identity = (
            self.intent.scope.owner.run_id,
            self.intent.scope.task.source_task_id,
            self.intent.request_id,
        )
        return hashlib.sha256(
            json.dumps(identity, separators=(",", ":")).encode()
        ).hexdigest()


class LocalActorExecution(Contract):
    schema_version: Literal["local-actor-execution/1"] = "local-actor-execution/1"
    call: LocalActorCall
    guard: ProcessOwnerGuard
    command_ref: EvidenceRef
    reply_ref: EvidenceRef
    response_ref: EvidenceRef
    output: LocalActorOutput
    dispatch_timing: ActorDispatchTiming | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = dict(handler(self))
        if self.dispatch_timing is None:
            result.pop("dispatch_timing", None)
        return result

    @model_validator(mode="after")
    def exact_refs(self) -> Self:
        window = self.call.intent.execution_window
        if (window is None) != (self.dispatch_timing is None):
            raise ValueError(
                "Actual dispatch timing required exactly for selected windows"
            )
        if self.dispatch_timing is not None and window is not None:
            self.dispatch_timing.require_original(self.call.intent.operation, window)
        for ref, schema in (
            (self.command_ref, "actor-worker-command/1"),
            (self.reply_ref, "actor-worker-reply/1"),
            (self.response_ref, "actor-model-response/1"),
        ):
            private_state_ref(ref, schema)
        return self
