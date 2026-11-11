"""Original worker exchange references; evidence is not execution permission."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .local_generator import LocalGeneratorIntent
from .lifecycle import AllocationToken
from .process_guard import ProcessOwnerGuard
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class GeneratorExecutionRecord(Contract):
    schema_version: Literal["generator-execution-record/1"] = (
        "generator-execution-record/1"
    )
    intent: LocalGeneratorIntent
    resource: AllocationToken
    spec_ref: EvidenceRef
    acquired_ref: EvidenceRef
    command_ref: EvidenceRef
    reply_ref: EvidenceRef
    guard: ProcessOwnerGuard

    @model_validator(mode="after")
    def original_owner(self) -> Self:
        if (
            self.resource.owner != self.intent.binding.owner
            or self.resource.resource_kind != "generator"
            or self.resource.scope != "batch"
        ):
            raise ValueError("Execution requires its original batch Generator owner")
        for ref, schema in (
            (self.spec_ref, "generator-resource-spec/3"),
            (self.acquired_ref, "generator-resource-fact/1"),
            (self.command_ref, "generator-worker-command/3"),
            (self.reply_ref, "generator-worker-reply/4"),
        ):
            private_state_ref(ref, schema)
        return self
