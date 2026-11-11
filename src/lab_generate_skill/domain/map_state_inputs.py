"""Bounded immutable Map state inputs; no native-file or execution permission."""

import hashlib
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .evidence_read_scope import EvidenceReadScope
from .identity import TaskIdentity
from .state_qualification import EnvironmentSelection, ResetSelection
from .state_scope import private_state_ref

MAX_MAP_STATE_INPUT_BYTES = 6 * 1024**2


class MapStateInputBody(Contract):
    reference: EvidenceRef
    text: str = Field(min_length=2, max_length=MAX_MAP_STATE_INPUT_BYTES)

    @model_validator(mode="after")
    def exact(self) -> Self:
        raw = self.text.encode()
        if (
            self.reference.visibility != "private"
            or self.reference.media_type != "application/json"
            or (len(raw), hashlib.sha256(raw).hexdigest())
            != (self.reference.size_bytes, self.reference.sha256)
        ):
            raise ValueError("Exact private Map state JSON bytes required")
        return self


class MapStateInputBodies(Contract):
    schema_version: Literal["map-state-input-bodies/1"] = "map-state-input-bodies/1"
    bodies: tuple[MapStateInputBody, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            len({x.reference for x in self.bodies}) != len(self.bodies)
            or sum(len(x.text.encode()) for x in self.bodies)
            > MAX_MAP_STATE_INPUT_BYTES
        ):
            raise ValueError("Distinct complete bounded Map state inputs required")
        return self


class MapStateInputsCommand(Contract):
    schema_version: Literal["map-state-inputs-command/1"] = "map-state-inputs-command/1"
    action: Literal["inputs", "check"]
    scope: EvidenceReadScope
    workspace_root: str = Field(min_length=1, max_length=4096)
    task: TaskIdentity
    selection: Annotated[
        EnvironmentSelection | ResetSelection, Field(discriminator="schema_version")
    ]
    selection_ref: EvidenceRef

    @model_validator(mode="after")
    def selected(self) -> Self:
        path = PurePosixPath(self.workspace_root)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Original absolute Map proof workspace required")
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("map", "navigation_page_identity", 1, "train"):
            raise ValueError("Only original Map navigation state inputs supported")
        private_state_ref(self.selection_ref, self.selection.schema_version)
        if (
            isinstance(self.selection, EnvironmentSelection)
            and self.selection.scope.task != self.task
        ):
            raise ValueError("Map state selection changed original task")
        if self.scope.binding.source_task_id not in (None, self.task.source_task_id):
            raise ValueError("Map state inputs changed metadata source task")
        return self
