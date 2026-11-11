"""Exact frozen-source/current-attempt joins for initial equivalence, no permit.

Original context/state bodies keep their original owner. New candidate facts
must come from the selected current scope; no source/initialization producer is
invoked by these pure joins. Actual permissions and native comparison are ports.
"""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .baseline import BaselineInputs
from .evidence import EvidenceRef
from .execution import AttemptBinding
from .execution_task_source import ExecutionTaskSource
from .errors import OwnershipConflict
from .public_context import PublicContextInputs, PublicContextReceipt
from .state_scope import StateScope, private_state_ref
from .validation import Contract


class InitialAdoptionBinding(Contract):
    schema_version: Literal["initial-adoption-binding/1"] = "initial-adoption-binding/1"
    scope: StateScope
    binding: AttemptBinding
    execution_source_ref: EvidenceRef
    source_context_ref: EvidenceRef

    @model_validator(mode="after")
    def current_attempt(self) -> Self:
        private_state_ref(self.execution_source_ref, "execution-task-source/2")
        private_state_ref(self.source_context_ref, "public-context-receipt/1")
        if (self.scope.owner, self.scope.task, self.scope.attempt_id) != (
            self.binding.run.owner,
            self.binding.task,
            self.binding.attempt_id,
        ) or self.scope.task.split != "train":
            raise OwnershipConflict(
                "Initial adoption requires the exact current train attempt"
            )
        return self


class InitialAdoptionInputs(Contract):
    binding: InitialAdoptionBinding
    source: ExecutionTaskSource

    @model_validator(mode="after")
    def exact_source(self) -> Self:
        selected, source = self.binding, self.source
        raw = source.model_dump_json().encode()
        if (
            source.schema_version != "execution-task-source/2"
            or source.frozen_origin is None
            or selected.binding != source.intent.binding
            or selected.source_context_ref != source.source_context_receipt_ref
            or selected.execution_source_ref.media_type != "application/json"
            or (len(raw), hashlib.sha256(raw).hexdigest())
            != (
                selected.execution_source_ref.size_bytes,
                selected.execution_source_ref.sha256,
            )
        ):
            raise OwnershipConflict(
                "Initial adoption changed its complete current Source2/claim binding"
            )
        return self

    def require_source(
        self,
        reference: EvidenceRef,
        receipt: PublicContextReceipt,
        inputs: PublicContextInputs,
    ) -> None:
        source = self.source
        origin = source.frozen_origin
        assert origin is not None
        parent = origin.validation.parent.record.binding
        raw = receipt.model_dump_json().encode()
        if (
            reference != self.binding.source_context_ref
            or reference.media_type != "application/json"
            or (len(raw), hashlib.sha256(raw).hexdigest())
            != (reference.size_bytes, reference.sha256)
            or receipt.scope.owner != parent.run.owner
            or receipt.scope.task != parent.task.identity
            or receipt.public_context_ref != source.intent.public_context_ref
            or receipt.spec_ref != parent.task.baseline_ref
            or inputs.baseline_inputs.binding != parent.task
        ):
            raise OwnershipConflict(
                "Adoption cannot retag or replace the original frozen source"
            )

    def require_candidate(self, candidate: BaselineInputs) -> None:
        if (
            candidate.prepared.scope != self.binding.scope
            or candidate.binding != self.source.task
        ):
            raise OwnershipConflict(
                "Initial adoption changed its current measured candidate/task"
            )

    def require_comparison(
        self, source: PublicContextInputs, candidate: BaselineInputs
    ) -> None:
        """Pure provenance join; caller must separately verify live adoption."""
        self.require_candidate(candidate)
        origin = self.source.frozen_origin
        assert origin is not None
        parent = origin.validation.parent.record.binding
        if (
            source.baseline.scope.owner != parent.run.owner
            or source.baseline.scope.task != parent.task.identity
            or source.baseline_inputs.prepared.scope != source.baseline.scope
            or source.baseline_inputs.binding != parent.task
            or source.context_ref != self.source.intent.public_context_ref
            or source.context.task != candidate.public_task
            or candidate.prepared.scope.owner == parent.run.owner
        ):
            raise OwnershipConflict(
                "Adopted comparison changed original source or current candidate"
            )
