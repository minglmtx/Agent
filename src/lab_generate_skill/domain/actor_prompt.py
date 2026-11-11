"""Public Actor projection data, independent of execution permissions and I/O."""

import json
import hashlib
from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_observation_view import ActorObservationView
from .actor_versions import actor_version_fields, actor_version_output
from .actor_observation_source import ActorObservationSource
from .observation import ResolvedObservation
from .optional_policies import InactivePolicy
from .skill import CompactSkill
from .task import PublicTask
from .validation import Contract, NonEmptyText

MAX_ACTOR_INPUT_BYTES = 8 * 1024 * 1024
MAX_ACTOR_RESPONSE_BYTES = 1024 * 1024


class ActorHistoryItem(Contract):
    schema_version: Literal["actor-history-item/2"] | None = None
    executed: bool | None = None
    action: str = Field(max_length=MAX_ACTOR_RESPONSE_BYTES)
    error: str = Field(max_length=65536)

    @model_serializer(mode="wrap")
    def original_history_wire(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version is None:
            result.pop("schema_version", None)
            result.pop("executed", None)
        return result

    @model_validator(mode="after")
    def explicit_execution_fact(self) -> Self:
        if (self.schema_version is None) != (self.executed is None):
            raise ValueError("History execution truth requires explicit item version2")
        return self


from .observation_viewport import VIEWPORT_NAME, viewport_reference


class ActorPublicTurn(Contract):
    """Only already-public facts; the caller verifies original trace lineage."""

    schema_version: Literal["actor-public-turn/1", "actor-public-turn/2"] = (
        "actor-public-turn/1"
    )
    task: PublicTask
    skill: CompactSkill
    observation: ResolvedObservation
    history: tuple[ActorHistoryItem, ...] = Field(max_length=10000)
    memory: InactivePolicy
    observation_source: ActorObservationSource | None = None

    @model_serializer(mode="wrap")
    def original_public_wire(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "actor-public-turn/1",
            ("observation_source",),
        )

    @model_validator(mode="after")
    def current_public_page(self) -> Self:
        old = self.schema_version == "actor-public-turn/1"
        actor_version_fields(
            self, old, ("observation_source",), record_name="Actor public turn"
        )
        if old != (self.observation_source is None):
            raise ValueError("Adaptive public source requires explicit public turn v2")
        observed = self.observation.record
        if observed.task != self.task.identity:
            raise ValueError("Actor observation must retain the public task")
        if observed.state != "ready" or self.observation.text is None:
            raise ValueError("Actor projection needs the actually available page text")
        if observed.artifacts:
            if any(artifact.name != VIEWPORT_NAME for artifact in observed.artifacts):
                raise ValueError(
                    "This text Actor protocol supports only public viewport metadata artifacts"
                )
            viewport_reference(
                observed
            )  # Scope/body is independently verified by its bounded reader.
        if self.observation_source is not None:
            source = self.observation_source
            snapshot = source.snapshot
            if (
                snapshot.scope.task,
                snapshot.scope.context_id,
                snapshot.scope.attempt_id,
                snapshot.sequence,
                snapshot.tab_id,
            ) != (
                observed.task,
                observed.context_id,
                observed.attempt_id,
                observed.sequence,
                observed.active_tab_id,
            ):
                raise ValueError(
                    "Adaptive source changed original public observation identity"
                )
            assert self.observation.text is not None
            if (
                snapshot.text_sha256
                != hashlib.sha256(self.observation.text.encode()).hexdigest()
            ):
                raise ValueError(
                    "Adaptive source changed complete original public text"
                )
            if source.local_window is not None:
                overview = source.local_window.overview
                if overview is None or (
                    overview.tabs,
                    overview.active_tab_id,
                    overview.last_action_error,
                ) != (
                    observed.tabs,
                    observed.active_tab_id,
                    observed.last_action_error,
                ):
                    raise ValueError(
                        "Adaptive window omitted or changed original public current state"
                    )
        if len(self.model_dump_json().encode()) > MAX_ACTOR_INPUT_BYTES:
            raise ValueError("Public Actor turn exceeds byte budget")
        return self


class ActorMessage(Contract):
    role: Literal["system", "user"]
    content: NonEmptyText


class ActorPrompt(Contract):
    schema_version: Literal["actor-model-input/1"] = "actor-model-input/1"
    prompt_version: Literal[
        "browsergym-baseline-full-ax-v1",
        "browsergym-map-rails-diagnostic-ax-v1",
        "browsergym-map-rails-diagnostic-ax-v2",
        "browsergym-adaptive-full-ax-v1",
        "browsergym-adaptive-local-ax-v1",
        "browsergym-adaptive-full-ax-v2",
        "browsergym-adaptive-local-ax-v2",
        "browsergym-adaptive-count-probe-v1",
        "browsergym-adaptive-count-probe-v2",
    ] = "browsergym-baseline-full-ax-v1"
    messages: tuple[ActorMessage, ActorMessage]
    observation_view: ActorObservationView | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self, handler, self.observation_view is None, ("observation_view",)
        )

    def input_bytes(self) -> bytes:
        """Only these exact bytes are model-visible; envelope fields are routing."""
        return json.dumps(
            {"messages": [m.model_dump() for m in self.messages]}, ensure_ascii=False
        ).encode()

    @model_validator(mode="after")
    def bounded_ordered_messages(self) -> Self:
        adaptive = self.prompt_version in (
            "browsergym-adaptive-full-ax-v1",
            "browsergym-adaptive-local-ax-v1",
            "browsergym-adaptive-full-ax-v2",
            "browsergym-adaptive-local-ax-v2",
            "browsergym-adaptive-count-probe-v1",
            "browsergym-adaptive-count-probe-v2",
        )
        actor_version_fields(
            self, not adaptive, ("observation_view",), record_name="Actor prompt"
        )
        if adaptive != (self.observation_view is not None):
            raise ValueError(
                "Adaptive Actor input requires its explicit versioned public view"
            )
        if self.observation_view is not None:
            mode = (
                "compact_full"
                if self.prompt_version
                in ("browsergym-adaptive-full-ax-v1", "browsergym-adaptive-full-ax-v2")
                else "local"
            )
            if self.observation_view.mode != mode:
                raise ValueError("Actor prompt version and observation mode disagree")
            new = self.prompt_version in (
                "browsergym-adaptive-full-ax-v2",
                "browsergym-adaptive-local-ax-v2",
                "browsergym-adaptive-count-probe-v2",
            )
            if new != (
                self.observation_view.schema_version == "actor-observation-view/3"
            ):
                raise ValueError(
                    "Prompt version changed its explicit tool-schema view contract"
                )
            self.observation_view.body(self.messages[1].content)
        if tuple(m.role for m in self.messages) != ("system", "user"):
            raise ValueError("Actor needs one system and one user message")
        if len(self.input_bytes()) > MAX_ACTOR_INPUT_BYTES:
            raise ValueError("Rendered Actor input exceeds byte budget")
        return self
