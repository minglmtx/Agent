"""Locked live trace history; pre-effect capacity and once-acknowledged intents.

This adapter never performs the registered side effect. Lost acknowledgement
requires inspecting the original intent/outcome; a replay is not another send.
Verified observations enter CAS before a snapshot commit can fail, preserving
original facts even when an unexpected oversized outcome cannot fit history.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.trace_journal_evidence import (
    TraceJournalEvidence,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.trace_events import (
    ActionPlanned,
    GenerationPlanned,
    GenerationObserved,
    DecisionRejected,
    TraceProgressEvent,
    ReadPlanned,
    ReadObserved,
)
from lab_generate_skill.domain.trace_journal import (
    TRACE_EVENT,
    TraceJournalCommitUnconfirmed,
    TraceSnapshot,
    append_trace_event,
    trace_event_replayed,
)
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.domain.trace_progress import check_trace_operation
from lab_generate_skill.ports.actor_context import (
    ActorGenerationInputReads,
    ActorDecisionInputReads,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.trace_journal import (
    TraceJournalAuthority,
    TraceReadingInputs,
)


class FileTraceJournal:
    def __init__(
        self,
        root: Path,
        plan: TracePlan,
        controls: OperationControls,
        evidence: EvidenceStore,
        authority: TraceJournalAuthority,
        *,
        generation_inputs: ActorGenerationInputReads | None = None,
        reading_inputs: TraceReadingInputs | None = None,
    ) -> None:
        self.plan = TracePlan.model_validate(plan)
        self.controls, self.evidence = controls, evidence
        self.verifier = TraceJournalEvidence(evidence, authority)
        if generation_inputs is not None and not callable(
            getattr(generation_inputs, "generation_inputs", None)
        ):
            raise TypeError("Original scoped generation input supplier required")
        self.generation_inputs = generation_inputs
        self.reading_inputs = reading_inputs
        key = [plan.scope.owner.run_id, plan.scope.attempt_id]
        name = (
            hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()
            + ".trace.json"
        )
        self.file = AtomicSnapshotFile(root, name, max_bytes=plan.capacity.max_bytes)

    def with_generation_inputs(
        self, inputs: ActorGenerationInputReads
    ) -> "FileTraceJournal":
        if inputs is None:
            raise TypeError("Explicit original generation input supplier required")
        return FileTraceJournal(
            self.file.root,
            self.plan,
            self.controls,
            self.evidence,
            self.verifier.authority,
            generation_inputs=inputs,
            reading_inputs=self.reading_inputs,
        )

    def with_reading_inputs(self, inputs: TraceReadingInputs) -> "FileTraceJournal":
        if inputs is None:
            raise TypeError("Original current reading input supplier required")
        return FileTraceJournal(
            self.file.root,
            self.plan,
            self.controls,
            self.evidence,
            self.verifier.authority,
            generation_inputs=self.generation_inputs,
            reading_inputs=inputs,
        )

    def _guard(self, op: OperationContext, *, read: bool = False) -> OperationControl:
        op = OperationContext.model_validate(op)
        if read and op.attempt_id is None:
            if (op.run_id, op.owner_id) != (
                self.plan.scope.owner.run_id,
                self.plan.scope.owner.owner_id,
            ):
                raise OwnershipConflict("Trace read changed original run/owner")
        else:
            check_trace_operation(self.plan, op)
        control = self.controls.bind(op)
        control.checkpoint()
        return control

    def _load(self, raw: bytes | None) -> TraceSnapshot | None:
        if raw is None:
            return None
        try:
            snapshot = TraceSnapshot.model_validate_json(raw)
        except (ValidationError, OwnershipConflict, InvalidTransition) as error:
            raise EvidenceIntegrityError("Invalid live trace snapshot") from error
        if snapshot.plan != self.plan:
            raise OwnershipConflict("Original live trace plan/capacity changed")
        return snapshot

    def _transaction(
        self,
        op: OperationContext,
        update: Callable[[TraceSnapshot | None, OperationControl], TraceSnapshot],
        *,
        read: bool = False,
    ) -> TraceSnapshot:
        control = self._guard(op, read=read)
        with self.file.locked(control) as transaction:
            before = self._load(transaction.read())
            after = update(before, control)
            if after != before:
                transaction.write(after.model_dump_json().encode())
            control.checkpoint()
        return after

    def create(self, plan: TracePlan, op: OperationContext) -> TraceSnapshot:
        plan = TracePlan.model_validate(plan)
        op = OperationContext.model_validate(op)
        if plan != self.plan:
            raise OwnershipConflict("Create differs from bound trace plan")
        candidate = TraceSnapshot(plan=plan, creation_operation=op, events=())

        def update(
            current: TraceSnapshot | None, control: OperationControl
        ) -> TraceSnapshot:
            if current is not None:
                if current.creation_operation != op:
                    raise OwnershipConflict(
                        "Trace creation must replay original command"
                    )
                return current
            self.verifier.plan(plan, op, control)
            return candidate

        return self._transaction(op, update)

    def read(self, op: OperationContext) -> TraceSnapshot:
        def update(
            current: TraceSnapshot | None, control: OperationControl
        ) -> TraceSnapshot:
            if current is None:
                raise EvidenceNotFound("Live trace has not been created")
            return current

        return self._transaction(op, update, read=True)

    def append(
        self, event: TraceProgressEvent, expected_revision: int, op: OperationContext
    ) -> TraceSnapshot:
        event = TRACE_EVENT.validate_python(event, strict=True)
        op = OperationContext.model_validate(op)
        reconciling = (
            op.mode == "cleanup"
            and op.parent_operation_id == event.operation.operation_id
            and (op.allocation_id, op.recovery_ref)
            == (event.operation.allocation_id, event.operation.recovery_ref)
        )
        if op != event.operation and not reconciling:
            raise OwnershipConflict(
                "Trace append requires exact event command or parent cleanup"
            )
        observed = not isinstance(
            event, (GenerationPlanned, ActionPlanned, ReadPlanned)
        )
        retained: EvidenceRef | None = None

        def update(
            current: TraceSnapshot | None, control: OperationControl
        ) -> TraceSnapshot:
            nonlocal retained
            if current is None:
                raise EvidenceNotFound("Create live trace before appending")
            if trace_event_replayed(current, event, expected_revision):
                return current
            if reconciling and not observed:
                raise OwnershipConflict("Cleanup cannot register new execution")
            inputs = None
            if not observed:
                candidate = append_trace_event(current, event, expected_revision)
                if (
                    isinstance(event, GenerationPlanned)
                    and self.generation_inputs is not None
                ):
                    inputs = self.generation_inputs.generation_inputs(
                        event.intent, control
                    )
                if inputs is None:
                    self.verifier.plan(self.plan, op, control)
                else:
                    self.verifier.plan(self.plan, op, control, generation_inputs=inputs)
            else:
                view = current.project()
                view.advance(self.plan, event)
                # Only the bounded snapshot constructor can authorize publication.
                # This temporary projection validates facts before capacity failure.
                candidate = current.model_copy(
                    update={"events": (*current.events, event)}
                )
            if (
                isinstance(event, GenerationObserved)
                and self.generation_inputs is not None
            ):
                intent = current.project().intent
                if intent is None or not intent.matches(event.generation):
                    raise OwnershipConflict(
                        "Result inputs require the exact pending generation"
                    )
                inputs = self.generation_inputs.generation_inputs(intent, control)
            if isinstance(event, DecisionRejected) and isinstance(
                self.generation_inputs, ActorDecisionInputReads
            ):
                generation = current.project().generation
                if (
                    generation is None
                    or generation.generation_id != event.decision.generation_id
                ):
                    raise OwnershipConflict(
                        "Rejection inputs changed original generation"
                    )
                inputs = self.generation_inputs.decision_inputs(generation, control)
            if isinstance(event, ReadObserved):
                if self.reading_inputs is None:
                    raise OwnershipConflict(
                        "Registered original readonly result verifier is required"
                    )
                self.reading_inputs.verify_reading(current, event, op, control)
                inputs = self.reading_inputs.reading_inputs(event, control)
            self.verifier.event(
                current, candidate, event, op, control, generation_inputs=inputs
            )
            if observed:
                retained = self.evidence.put(
                    event.model_dump_json().encode(),
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="trace-journal-event/1",
                        visibility="private",
                        producer="trace-journal-v1",
                    ),
                    control=control,
                )
                control.checkpoint()
                candidate = append_trace_event(current, event, expected_revision)
            return candidate

        try:
            return self._transaction(op, update)
        except Exception as error:
            if retained is not None:
                raise TraceJournalCommitUnconfirmed(retained) from error
            raise
