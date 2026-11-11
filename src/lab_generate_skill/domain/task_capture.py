"""Frozen terminal collection policy; actual initialization is resolved later."""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .validation import Contract, Identifier, NonEmptyText
from .state_scope import StateScope, private_state_ref
from .evidence import EvidenceRef, EvidenceRequirements
from .initial_observation import InitialObservationSelection
from .task_execution import InitializedTask


class TaskCapturePlan(Contract):
    schema_version: Literal["task-capture-plan/1", "task-capture-plan/2"] = (
        "task-capture-plan/1"
    )
    scope: StateScope
    requirements: EvidenceRequirements
    page_operation_id: Identifier
    close_operation_id: Identifier
    guard_operation_id: Identifier
    page_collector_id: Identifier
    page_collector_version: NonEmptyText
    guard_collector_id: Identifier
    guard_collector_version: NonEmptyText
    close_seconds: int = Field(ge=1, le=60)
    metadata_close_seconds: int | None = Field(default=None, ge=1, le=3600)

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.schema_version == "task-capture-plan/1":
            data.pop("metadata_close_seconds", None)
        return data

    @model_validator(mode="after")
    def stages(self) -> Self:
        if self.schema_version == "task-capture-plan/1":
            if "metadata_close_seconds" in self.model_fields_set:
                raise ValueError("Original capture plan forbids metadata budget fields")
        elif (
            self.metadata_close_seconds is None
            or self.metadata_close_seconds < self.close_seconds
        ):
            raise ValueError(
                "Version2 requires an explicit sufficient metadata close budget"
            )
        if self.scope.task.split != "train":
            raise ValueError("Current construction capture is train-only")
        ids = (self.page_operation_id, self.close_operation_id, self.guard_operation_id)
        if any(len(name) > 200 for name in ids):
            raise ValueError(
                "Capture identities must reserve room for original proof reads"
            )
        if len(set(ids)) != 3:
            raise ValueError("Original terminal/close/guard identities must differ")
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Complete capture declaration exceeds 2MiB")
        return self


class TaskCaptureInputs(Contract):
    schema_version: Literal["task-capture-inputs/1"] = "task-capture-inputs/1"
    initialized: InitializedTask
    initial: InitialObservationSelection
    initial_capture_intent_ref: EvidenceRef
    initial_capture_result_ref: EvidenceRef
    initial_checks_ref: EvidenceRef
    environment_selection_ref: EvidenceRef
    prepare_request_ref: EvidenceRef

    @model_validator(mode="after")
    def actual_inputs(self) -> Self:
        if self.initialized.actor.schema_version != "actor-run-request/2":
            raise ValueError("Current capture requires original v2 initialized Actor")
        for ref, schema in (
            (self.initial_capture_intent_ref, "browser-capture-intent/1"),
            (self.initial_capture_result_ref, "browser-capture-result/1"),
            (self.initial_checks_ref, "initial-state-checks/1"),
            (self.environment_selection_ref, "environment-selection/1"),
            (self.prepare_request_ref, "site-task-request/2"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json" or ref.size_bytes == 0:
                raise ValueError("Original nonempty complete terminal input required")
        return self
