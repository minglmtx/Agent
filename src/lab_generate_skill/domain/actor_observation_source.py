"""Public snapshot/window source facts, separate from permissions/native counts."""

from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .actor_proposal_feedback import ActorInvalidProposalProgress
from .evidence import EvidenceRef
from .observation_read import PublicObservationSnapshot, ObservationReadPayload
from .observation_read_policy import ObservationReadPolicy
from .validation import Contract, Identifier


class ActorObservationSource(Contract):
    schema_version: Literal[
        "actor-observation-source/1", "actor-observation-source/2"
    ] = "actor-observation-source/1"
    invalid_proposals: ActorInvalidProposalProgress | None = None
    snapshot: PublicObservationSnapshot
    policy: ObservationReadPolicy
    eligibility: Literal["local_supported", "full_required"]
    reason: Identifier
    tools: tuple[Literal["list_regions", "read_region", "search_regions"], ...] = Field(
        max_length=3
    )
    local_window: ObservationReadPayload | None
    window_origin: Literal["automatic_initial", "actor_returned", "none"]
    read_result_ref: EvidenceRef | None
    reads_used: int = Field(ge=0, le=64)
    no_progress: int = Field(ge=0, le=64)

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version == "actor-observation-source/1":
            result.pop("invalid_proposals", None)
        return result

    @model_validator(mode="after")
    def source_window_is_not_delivery(self) -> Self:
        if self.schema_version == "actor-observation-source/1":
            if (
                "invalid_proposals" in self.model_fields_set
                or self.policy.schema_version != "observation-read-policy/1"
            ):
                raise ValueError(
                    "Original source1 cannot carry new rejection policy/facts"
                )
        elif (
            self.invalid_proposals is None
            or self.policy.schema_version != "observation-read-policy/2"
        ):
            raise ValueError(
                "Source2 requires its frozen policy2 and actual rejection facts"
            )
        if self.snapshot.policy_sha256 != self.policy.digest or len(
            set(self.tools)
        ) != len(self.tools):
            raise ValueError(
                "Public window changed frozen policy or repeated a registered tool"
            )
        if (
            self.reads_used > self.policy.reads_per_observation
            or self.no_progress > self.reads_used
        ):
            raise ValueError("Public window changed original read quota/progress")
        if self.eligibility == "local_supported":
            if (
                not self.tools
                or self.local_window is None
                or self.window_origin == "none"
            ):
                raise ValueError(
                    "Local source requires actual registered reader and explicit window"
                )
            if self.snapshot.structure != "browsergym_tab_ax/1":
                raise ValueError(
                    "Unindexed public structure cannot become a local reading source"
                )
        elif (
            self.tools
            or self.local_window is not None
            or self.window_origin != "none"
            or self.read_result_ref is not None
        ):
            raise ValueError(
                "Full-required source cannot pretend to have a local reader"
            )
        if self.local_window is not None:
            if (
                self.local_window.request.snapshot != self.snapshot
                or self.local_window.overview is None
            ):
                raise ValueError(
                    "Local source needs exact same-snapshot current overview and ranges"
                )
        if (self.window_origin == "actor_returned") != (
            self.read_result_ref is not None
        ):
            raise ValueError(
                "Only an actual returned reading has an original result reference"
            )
        if self.read_result_ref is not None and (
            self.read_result_ref.visibility != "public"
            or self.read_result_ref.content_schema != "observation-read-result/2"
        ):
            raise ValueError("Original complete public read result v2 required")
        if self.window_origin == "automatic_initial" and (
            self.reads_used or self.no_progress
        ):
            raise ValueError(
                "Automatic initial view is not an Actor tool call or checked content"
            )
        return self
