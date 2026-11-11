"""Same-task terminal proof inputs and immutable bodies; no live permission."""

import json
from typing import Literal, Self
from pathlib import PurePosixPath
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .evaluation import EvaluationContract
from .initial_observation import InitialObservationInputs
from .lifecycle import OperationContext
from .evidence_read_scope import EvidenceReadScope
from .errors import OwnershipConflict
from .verified_evidence_body import VerifiedEvidenceBody

TERMINAL_READ_BINDINGS = {
    (
        "shopping_admin",
        "page_navigation",
        1,
        "train",
    ): "admin-navigation-terminal-selection/1",
    (
        "map",
        "navigation_page_identity",
        1,
        "train",
    ): "map-navigation-terminal-selection/1",
}


class TerminalReadRequest(Contract):
    schema_version: Literal["terminal-read-request/1"] = "terminal-read-request/1"
    terminal_ref: EvidenceRef
    contract: EvaluationContract
    initial: InitialObservationInputs
    operation: OperationContext

    @model_validator(mode="after")
    def original(self) -> Self:
        scope = self.initial.prepared.scope
        task = scope.task
        binding = task.site, task.family, task.contract_version, task.split
        expected = TERMINAL_READ_BINDINGS.get(binding)
        if expected is None or (
            self.terminal_ref.content_schema,
            self.terminal_ref.visibility,
            self.terminal_ref.media_type,
        ) != (expected, "private", "application/json"):
            raise OwnershipConflict("Exact supported terminal task/schema required")
        if (
            self.contract.identity != task
            or self.contract.attempt_id != scope.attempt_id
            or self.contract.task_contract_ref != self.initial.prepared.task_binding_ref
            or self.contract.completion_spec_ref
            != self.initial.prepared.private_checks_ref
            or (
                self.operation.run_id,
                self.operation.owner_id,
                self.operation.attempt_id,
            )
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
        ):
            raise OwnershipConflict("Terminal read changed original task/attempt")
        initial = self.initial
        for reference, value in (
            (initial.selection.preparation.prepared_ref, initial.prepared),
            (initial.prepared.spec_ref, initial.spec),
            (initial.selection.browser_spec_ref, initial.browser),
            (initial.acquired.details.started.initial_return_ref, initial.returned),
            (
                initial.acquired.details.started.initial_observation_ref,
                initial.observation.record,
            ),
        ):
            VerifiedEvidenceBody(reference, value.model_dump_json().encode())
        # Original resource-fact wire is sorted, spaced JSON, unlike the typed
        # strict view's compact serialization. Preserve the published bytes.
        VerifiedEvidenceBody(
            initial.selection.browser_acquired_ref,
            json.dumps(
                initial.acquired.model_dump(mode="json"), sort_keys=True
            ).encode(),
        )
        return self


class TerminalReadCommand(Contract):
    schema_version: Literal["terminal-read-command/1"] = "terminal-read-command/1"
    scope: EvidenceReadScope
    workspace_root: str = Field(min_length=1, max_length=4096)
    purpose: Literal["same_task", "retained_data"] = "same_task"
    request: TerminalReadRequest

    @model_validator(mode="after")
    def owner(self) -> Self:
        original = self.request.initial.prepared.scope
        path = PurePosixPath(self.workspace_root)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Original absolute workspace required")
        if self.purpose == "same_task" and self.scope.binding.owner != original.owner:
            raise OwnershipConflict("Terminal proof changed original namespace owner")
        if self.scope.binding.source_task_id not in (
            None,
            original.task.source_task_id,
        ):
            raise OwnershipConflict("Terminal proof changed namespace task")
        if (
            self.purpose == "same_task"
            and self.scope.config.installation
            != self.request.initial.browser.configuration.installation
        ):
            raise OwnershipConflict("Terminal proof changed original installed release")
        return self


class TerminalEvidenceBody(Contract):
    reference: EvidenceRef
    json_text: str = Field(min_length=1, max_length=13 * 1024**2)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.reference.media_type != "application/json":
            raise ValueError("Terminal handoff contains JSON bodies only")
        VerifiedEvidenceBody(self.reference, self.json_text.encode())
        return self


class TerminalReadBodies(Contract):
    schema_version: Literal["terminal-read-bodies/1"] = "terminal-read-bodies/1"
    request: TerminalReadRequest
    purpose: Literal["same_task", "retained_data"] = "same_task"
    bodies: tuple[TerminalEvidenceBody, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def exact(self) -> Self:
        refs = [value.reference for value in self.bodies]
        if len(set(refs)) != len(refs) or self.request.terminal_ref not in refs:
            raise ValueError(
                "Unique complete terminal bodies including selection required"
            )
        if sum(value.reference.size_bytes for value in self.bodies) > 13 * 1024**2:
            raise ValueError("Terminal body handoff exceeds its complete bound")
        return self
