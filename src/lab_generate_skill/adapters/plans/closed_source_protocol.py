"""Bounded fixed readonly source proof wire; errors never imply qualification."""

from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.closed_source_read import ClosedSourceReadCommand
from lab_generate_skill.domain.public_context import (
    PublicContextReceipt,
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.task_publication import TaskBindingInputs
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.claims import SourceClaimReceipt, check_source_claim
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionBodies
from lab_generate_skill.domain.preparation_read import PreparationReadBodies
from lab_generate_skill.domain.baseline_read import BaselineReadBodies
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)

ENTRY = "lab_generate_skill.bootstrap.closed_map_source_read"
MAX_PACKET = 13 * 1024**2


class ClosedSourceBindingBodies(Contract):
    """Exact immutable dependency bytes from one original supervised proof."""

    binding: TaskBinding
    public_task_json: str = Field(min_length=1, max_length=2 * 1024**2)
    private_spec_json: str = Field(min_length=1, max_length=2 * 1024**2)
    baseline_json: str = Field(min_length=1, max_length=2 * 1024**2)

    @model_validator(mode="after")
    def complete(self) -> Self:
        for ref, raw in (
            (self.binding.public_task_ref, self.public_task_json),
            (self.binding.private_spec_ref, self.private_spec_json),
            (self.binding.baseline_ref, self.baseline_json),
        ):
            require_complete_bytes(ref, raw.encode())
        public = PublicTask.model_validate_json(self.public_task_json)
        if public.identity != self.binding.identity:
            raise ValueError("Supervised public body changed original task identity")
        return self

    def inputs(self) -> TaskBindingInputs:
        return TaskBindingInputs(
            self.binding,
            PublicTask.model_validate_json(self.public_task_json),
            self.private_spec_json.encode(),
            self.baseline_json.encode(),
        )


class ClosedSourceReadReply(Contract):
    schema_version: Literal[
        "closed-source-read-reply/1",
        "closed-source-read-reply/2",
        "closed-source-read-reply/3",
        "closed-source-read-reply/4",
        "closed-source-read-reply/5",
        "closed-source-read-reply/6",
    ] = "closed-source-read-reply/1"
    request_sha256: Sha256
    worker: ProcessIdentity
    installed_sources: InstalledReleaseSources | None
    context: PublicContextReceipt | None
    binding: TaskBinding | None
    error: RemoteError | None
    publication_verified: bool = False
    read_count: int = Field(default=0, ge=0)
    body_read_count: int | None = Field(default=None, ge=0)
    unique_objects: int = Field(default=0, ge=0)
    plan_inputs_sha256: Sha256 | None = None
    binding_reference: EvidenceRef | None = None
    execution_source: ExecutionSourceFacts | None = None
    execution_claim: SourceClaimReceipt | None = None
    binding_bodies: ClosedSourceBindingBodies | None = None
    context_inputs: PublicContextInputs | None = None
    actor_bodies: ActorAcquisitionBodies | None = None
    preparation_bodies: PreparationReadBodies | None = None
    baseline_bodies: BaselineReadBodies | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.body_read_count is None:
            value.pop("body_read_count", None)
        if self.plan_inputs_sha256 is None:
            value.pop("plan_inputs_sha256", None)
        if self.binding_reference is None:
            value.pop("binding_reference", None)
        if self.execution_source is None:
            value.pop("execution_source", None)
        if self.execution_claim is None:
            value.pop("execution_claim", None)
        if self.binding_bodies is None:
            value.pop("binding_bodies", None)
        if self.context_inputs is None:
            value.pop("context_inputs", None)
        if self.actor_bodies is None:
            value.pop("actor_bodies", None)
        if self.preparation_bodies is None:
            value.pop("preparation_bodies", None)
        if self.baseline_bodies is None:
            value.pop("baseline_bodies", None)
        return value

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
            if (
                self.context is not None
                or self.binding is not None
                or self.publication_verified
                or self.plan_inputs_sha256 is not None
                or self.binding_reference is not None
                or self.execution_source is not None
                or self.execution_claim is not None
                or self.binding_bodies is not None
                or self.context_inputs is not None
                or self.actor_bodies is not None
                or self.preparation_bodies is not None
                or self.baseline_bodies is not None
            ):
                raise ValueError("Failed read cannot carry successful source facts")
        elif self.installed_sources is None or self.context is None:
            raise ValueError(
                "Successful source read requires installed and full source proof"
            )
        if self.context_inputs is not None and (
            self.context is None
            or assemble_public_context(self.context_inputs, self.context.operation)
            != self.context
        ):
            raise ValueError("Context input proof changed original complete context")
        if self.binding_reference is not None and self.binding is None:
            raise ValueError("Verified task reference requires its original binding")
        if self.binding_bodies is not None:
            if (
                self.schema_version != "closed-source-read-reply/2"
                or self.binding_reference is None
                or self.binding != self.binding_bodies.binding
            ):
                raise ValueError(
                    "Exact supervised binding bodies require version2 reference proof"
                )
        elif self.schema_version == "closed-source-read-reply/2":
            raise ValueError("Version2 source reply requires complete binding bodies")
        if (self.schema_version == "closed-source-read-reply/3") != (
            self.actor_bodies is not None
        ):
            raise ValueError(
                "Version3 source reply requires exact Actor acquisition bodies"
            )
        if (self.schema_version == "closed-source-read-reply/4") != (
            self.preparation_bodies is not None
        ):
            raise ValueError("Version4 requires complete preparation input bodies")
        if (self.schema_version == "closed-source-read-reply/5") != (
            self.baseline_bodies is not None
        ):
            raise ValueError("Version5 requires complete baseline input bodies")
        if (self.schema_version == "closed-source-read-reply/6") != (
            self.execution_claim is not None
        ):
            raise ValueError("Version6 requires the exact execution claim body")
        if self.execution_claim is not None:
            facts = self.execution_source
            if (
                facts is None
                or self.execution_claim.reference
                != facts.source.intent.binding.claim_ref
            ):
                raise ValueError("Claim proof changed original execution reference")
            check_source_claim(
                self.execution_claim.record,
                self.execution_claim.reference,
                facts.source.run,
                facts.source.task,
            )
        if self.body_read_count is not None and self.body_read_count > self.read_count:
            raise ValueError("Completed physical body reads exceed logical reads")
        if self.unique_objects > self.read_count:
            raise ValueError("Unique read objects exceed complete reads")
        return self


def encode_command(command: ClosedSourceReadCommand) -> bytes:
    raw = ClosedSourceReadCommand.model_validate(command).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete closed source request exceeds its bound")
    return raw


def decode_command(raw: bytes) -> ClosedSourceReadCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Complete bounded source request required")
    value = ClosedSourceReadCommand.model_validate_json(raw)
    if encode_command(value) != raw:
        raise ValueError("Closed source request must retain canonical bytes")
    return value


def encode_reply(reply: ClosedSourceReadReply) -> bytes:
    raw = ClosedSourceReadReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_PACKET:
        raise ValueError("Complete closed source reply exceeds its bound")
    return raw
