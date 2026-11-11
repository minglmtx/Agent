"""Recorded Actor model call and parsed decision; not shared budget settlement."""

from typing import Literal, Self, Any
from pydantic import model_validator, model_serializer, SerializerFunctionWrapHandler
from .actor_versions import actor_version_fields, actor_version_output
from .actor_execution_window import ActorGenerationWindow
from .browser import BrowserAction, observation_reference
from .evidence import EvidenceRef
from .state_scope import StateFact, private_state_ref
from .validation import Contract, Identifier
from .observation_read import ObservationReadRequest, ObservationSourceSpan
from pydantic import Field
from .validation import Sha256
from .observation_read_policy import ObservationReadPolicy


class ActorGeneration(StateFact):
    """An actually attempted call; not a planned or budget-only reservation."""

    schema_version: Literal["actor-generation/1", "actor-generation/2"] = (
        "actor-generation/1"
    )
    context_preparation_ref: EvidenceRef | None = None
    generation_id: Identifier
    request_id: Identifier
    before_observation_ref: EvidenceRef
    input_ref: EvidenceRef
    parameters_ref: EvidenceRef
    status: Literal["completed", "failed", "uncertain"]
    response_ref: EvidenceRef | None = None
    failure_ref: EvidenceRef | None = None

    execution_window: ActorGenerationWindow | None = None

    @model_serializer(mode="wrap")
    def wire_version(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = actor_version_output(
            self,
            handler,
            self.schema_version == "actor-generation/1",
            ("context_preparation_ref",),
        )

        if self.execution_window is None:
            result.pop("execution_window", None)
        return result

    @model_validator(mode="after")
    def actual_call_evidence(self) -> Self:
        actor_version_fields(
            self,
            self.schema_version == "actor-generation/1",
            ("context_preparation_ref",),
        )
        if (self.schema_version == "actor-generation/2") != (
            self.context_preparation_ref is not None
        ):
            raise ValueError(
                "Actor generation v2 requires its original preparation reference"
            )
        if self.context_preparation_ref is not None:
            private_state_ref(self.context_preparation_ref, "context-preparation/2")
        if self.execution_window is not None:
            self.execution_window.require_original(self.operation)
        observation_reference(self.before_observation_ref)
        private_state_ref(self.input_ref, "actor-model-input/1")
        private_state_ref(self.parameters_ref, "model-parameters/1")
        if self.response_ref is not None:
            private_state_ref(self.response_ref, "actor-model-response/1")
        if self.failure_ref is not None:
            private_state_ref(self.failure_ref, "generation-failure/1")
        if self.status == "completed":
            if self.response_ref is None or self.failure_ref is not None:
                raise ValueError("Completed generation requires response, not failure")
        elif self.failure_ref is None or self.response_ref is not None:
            raise ValueError("Failed/uncertain generation requires diagnostic evidence")
        return self


class ActorDecision(Contract):
    schema_version: Literal["actor-decision/1", "actor-decision/2"] = "actor-decision/1"
    generation_id: Identifier
    outcome: Literal["action", "invalid", "read"]
    action: BrowserAction | None = None
    failure_ref: EvidenceRef | None = None
    read_request: ObservationReadRequest | None = None
    read_policy: ObservationReadPolicy | None = None
    displayed_source_spans: tuple[ObservationSourceSpan, ...] | None = Field(
        default=None, max_length=2048
    )
    active_read_ref: EvidenceRef | None = None
    active_progress_fingerprint: Sha256 | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "actor-decision/1",
            (
                "read_request",
                "read_policy",
                "displayed_source_spans",
                "active_read_ref",
                "active_progress_fingerprint",
            ),
        )

    @model_validator(mode="after")
    def parsed_outcome(self) -> Self:
        actor_version_fields(
            self,
            self.schema_version == "actor-decision/1",
            (
                "read_request",
                "read_policy",
                "displayed_source_spans",
                "active_read_ref",
                "active_progress_fingerprint",
            ),
            record_name="Actor decision",
        )
        if (self.schema_version == "actor-decision/2") != (self.outcome == "read"):
            raise ValueError(
                "Read decision requires its explicit version; action/invalid keep original wire"
            )
        if self.outcome == "read":
            if (
                self.read_request is None
                or self.read_policy is None
                or self.displayed_source_spans is None
                or self.action is not None
                or self.failure_ref is not None
            ):
                raise ValueError(
                    "Read decision requires original snapshot/request/policy, no browser action or parse failure"
                )
            if self.read_request.snapshot.policy_sha256 != self.read_policy.digest:
                raise ValueError("Read decision changed frozen observation policy")
            if self.active_read_ref is not None and (
                self.active_read_ref.visibility != "public"
                or self.active_read_ref.content_schema != "observation-read-result/2"
            ):
                raise ValueError("Original active read model-input reference required")
            return self
        if self.failure_ref is not None:
            private_state_ref(self.failure_ref, "actor-parse-failure/1")
        if self.outcome == "action":
            if self.action is None or self.failure_ref is not None:
                raise ValueError("Valid decision requires action without parse failure")
        elif self.action is not None or self.failure_ref is None:
            raise ValueError("Invalid decision requires parse failure, not an action")
        return self
