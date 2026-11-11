"""Explicit public view provenance inside the exact Actor input envelope."""

import hashlib
from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .actor_versions import actor_version_fields, actor_version_output
from .evidence import EvidenceRef
from .observation_read import PublicObservationSnapshot, ObservationSourceSpan
from .observation_read_policy import ObservationReadPolicy
from .actor_proposal_feedback import ActorInvalidProposalProgress
from .validation import Contract, Identifier, Sha256

ObservationReadTool = Literal["list_regions", "read_region", "search_regions"]


class ActorObservationView(Contract):
    schema_version: Literal[
        "actor-observation-view/1",
        "actor-observation-view/2",
        "actor-observation-view/3",
    ] = "actor-observation-view/1"
    snapshot: PublicObservationSnapshot
    policy: ObservationReadPolicy
    mode: Literal["compact_full", "local"]
    source_spans: tuple[ObservationSourceSpan, ...] = Field(max_length=2048)
    body_start: int = Field(ge=0)
    body_end: int = Field(ge=0)
    body_sha256: Sha256
    body_token_limit: int | None = Field(ge=1, le=61440)
    tools: tuple[ObservationReadTool, ...] = Field(max_length=3)
    read_result_ref: EvidenceRef | None
    reads_used: int = Field(ge=0, le=64)
    no_progress: int = Field(ge=0, le=64)
    omissions: tuple[Identifier, ...] = Field(max_length=64)
    progress_fingerprint: Sha256 | None = None
    tab_count: int | None = Field(default=None, ge=1)
    invalid_proposals: ActorInvalidProposalProgress | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = actor_version_output(
            self,
            handler,
            self.schema_version == "actor-observation-view/1",
            ("progress_fingerprint",),
        )
        if self.schema_version != "actor-observation-view/3":
            result.pop("tab_count", None)
            result.pop("invalid_proposals", None)
        return result

    @model_validator(mode="after")
    def exact_view_scope(self) -> Self:
        if self.schema_version == "actor-observation-view/3":
            if (
                self.tab_count is None
                or self.invalid_proposals is None
                or self.policy.schema_version != "observation-read-policy/2"
            ):
                raise ValueError(
                    "View3 requires actual tabs, rejection facts and frozen policy2"
                )
        elif (
            any(
                name in self.model_fields_set
                for name in ("tab_count", "invalid_proposals")
            )
            or self.policy.schema_version != "observation-read-policy/1"
        ):
            raise ValueError("Original view forbids new schema-policy facts")
        actor_version_fields(
            self,
            self.schema_version == "actor-observation-view/1",
            ("progress_fingerprint",),
            record_name="Actor observation view",
        )
        if (
            self.schema_version
            in ("actor-observation-view/2", "actor-observation-view/3")
            and self.mode == "local"
            and self.progress_fingerprint is None
        ):
            raise ValueError(
                "Actual local view requires original reading coverage fingerprint"
            )
        if self.snapshot.policy_sha256 != self.policy.digest:
            raise ValueError("View changed original frozen observation policy")
        if self.body_end < self.body_start or len(set(self.tools)) != len(self.tools):
            raise ValueError(
                "Original ordered view range and unique registered tools required"
            )
        if self.mode == "local":
            if (
                self.body_token_limit != self.policy.body_max_tokens
                or not self.omissions
                or not self.tools
            ):
                raise ValueError(
                    "Local view requires explicit capacity, omissions and actual registered reader"
                )
        elif self.body_token_limit is not None or self.omissions:
            raise ValueError(
                "Complete view cannot masquerade as a partial reading window"
            )
        if self.snapshot.structure == "opaque_public_text/1" and (
            self.mode != "compact_full" or self.tools
        ):
            raise ValueError(
                "Unindexed public text cannot declare local reading capability"
            )
        if (
            self.reads_used > self.policy.reads_per_observation
            or self.no_progress > self.reads_used
        ):
            raise ValueError("View changed original read quota/progress facts")
        if self.read_result_ref is not None and (
            self.read_result_ref.visibility != "public"
            or self.read_result_ref.content_schema
            not in ("observation-read-result/1", "observation-read-result/2")
        ):
            raise ValueError("Original public same-snapshot read result required")
        return self

    def body(self, user_message: str) -> str:
        if type(user_message) is not str or self.body_end > len(user_message):
            raise ValueError("Observation body left actual Actor user message")
        body = user_message[self.body_start : self.body_end]
        if hashlib.sha256(body.encode()).hexdigest() != self.body_sha256:
            raise ValueError("Actual Actor observation body changed")
        return body
