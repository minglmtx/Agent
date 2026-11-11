"""Atomic per-run/source construction snapshot; never executes model work.

One trusted root and key across all writers; full plan/capacity is immutable.
The shared byte primitive supplies lock/fsync/replace/initialization integrity.
Verified observed facts are retained in CAS before commit and acknowledged only
after transaction cleanup. Read/exact replay never authorizes external effects.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from lab_generate_skill.adapters.plans.construction_evidence import ConstructionEvidence
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    AttemptResolved,
    CallCompleted,
    CallUncertain,
    ConstructionPlan,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_journal import (
    ConstructionCapacity,
    ConstructionCommitUnconfirmed,
    ConstructionSnapshot,
)
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    append_construction_event,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.construction import ConstructionAuthority
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier

_EVENT: TypeAdapter[ProgressEvent] = TypeAdapter(ProgressEvent)


class FileConstructionJournal:
    def __init__(
        self,
        root: Path,
        plan: ConstructionPlan,
        capacity: ConstructionCapacity,
        controls: OperationControls,
        evidence: EvidenceStore,
        plans: RunPlans,
        authority: ConstructionAuthority,
        contexts: ContextRecords,
        retrieval: RetrievalRecords,
        claims: SourceClaims,
        *,
        teacher_review: TeacherConstructionVerifier | None = None,
    ) -> None:
        self.plan = ConstructionPlan.model_validate(plan)
        self.capacity = ConstructionCapacity.model_validate(capacity)
        self.controls, self.evidence = controls, evidence
        self.verifier = ConstructionEvidence(
            evidence, plans, authority, contexts, retrieval, claims, teacher_review
        )
        identity = [self.plan.run.owner.run_id, self.plan.task.identity.source_task_id]
        name = (
            hashlib.sha256(
                json.dumps(identity, separators=(",", ":")).encode()
            ).hexdigest()
            + ".construction.json"
        )
        self.file = AtomicSnapshotFile(root, name, max_bytes=self.capacity.max_bytes)

    def _guard(self, op: OperationContext) -> OperationControl:
        op = OperationContext.model_validate(op)
        owner = self.plan.run.owner
        if (op.run_id, op.owner_id) != (
            owner.run_id,
            owner.owner_id,
        ) or op.attempt_id is not None:
            raise OwnershipConflict("Construction command requires its run-level owner")
        control = self.controls.bind(op)
        control.checkpoint()
        return control

    def _load(self, raw: bytes | None) -> ConstructionSnapshot | None:
        if raw is None:
            return None
        try:
            snapshot = ConstructionSnapshot.model_validate_json(raw)
        except (ValidationError, OwnershipConflict) as error:
            raise EvidenceIntegrityError("Invalid construction snapshot") from error
        if snapshot.progress.plan != self.plan or snapshot.capacity != self.capacity:
            raise OwnershipConflict("Construction plan or storage capacity changed")
        return snapshot

    def _transaction(
        self,
        op: OperationContext,
        update: Callable[
            [ConstructionSnapshot | None, OperationControl], ConstructionSnapshot
        ],
    ) -> ConstructionProgress:
        control = self._guard(op)
        with self.file.locked(control) as transaction:
            before = self._load(transaction.read())
            after = update(before, control)
            if after != before:
                transaction.write(after.model_dump_json().encode())
            control.checkpoint()
        return after.progress

    def create(
        self, plan: ConstructionPlan, op: OperationContext
    ) -> ConstructionProgress:
        plan = ConstructionPlan.model_validate(plan)
        op = OperationContext.model_validate(op)
        if plan != self.plan:
            raise OwnershipConflict("Create plan differs from bound construction")
        candidate = ConstructionSnapshot(
            capacity=self.capacity,
            creation_operation=op,
            progress=ConstructionProgress(plan=plan),
        )

        def update(
            current: ConstructionSnapshot | None, control: OperationControl
        ) -> ConstructionSnapshot:
            if current is not None:
                if current.creation_operation != op:
                    raise OwnershipConflict("Create must replay the original operation")
                return current
            self.verifier.plan(plan, op, control)
            return candidate

        return self._transaction(op, update)

    def read(self, op: OperationContext) -> ConstructionProgress:
        def update(
            current: ConstructionSnapshot | None, control: OperationControl
        ) -> ConstructionSnapshot:
            if current is None:
                raise EvidenceNotFound("Construction has not been created")
            return current

        return self._transaction(op, update)

    def verify_source(self, op: OperationContext) -> ConstructionProgress:
        """Reuse full original plan/claim/context/private input verification.

        Never turn ordinary read into a new-work check: cleanup and exact old
        facts retain their existing read path when source permission is denied.
        A concurrent history change refuses the proof; it never retries work.
        """
        control = self._guard(op)
        before = self.read(op)
        self.verifier.plan(before.plan, op, control)
        after = self.read(op)
        control.checkpoint()
        if after != before:
            raise RevisionConflict("Construction changed during source verification")
        return before

    def append(
        self, event: ProgressEvent, expected_revision: int, op: OperationContext
    ) -> ConstructionProgress:
        event = _EVENT.validate_python(event, strict=True)
        op = OperationContext.model_validate(op)
        reconciling = (
            op.mode == "cleanup"
            and op.parent_operation_id == event.operation.operation_id
            and (op.allocation_id, op.recovery_ref)
            == (event.operation.allocation_id, event.operation.recovery_ref)
        )
        if event.operation != op and not reconciling:
            raise OwnershipConflict("Append must use the exact event operation")
        if type(expected_revision) is not int or expected_revision < -1:
            raise ValueError("Invalid construction revision")
        retained: EvidenceRef | None = None

        def update(
            current: ConstructionSnapshot | None, control: OperationControl
        ) -> ConstructionSnapshot:
            nonlocal retained
            if current is None:
                raise EvidenceNotFound("Create construction before appending")
            if event.operation.operation_id == current.creation_operation.operation_id:
                raise OwnershipConflict("Creation operation cannot be reused")
            progress = append_construction_event(
                current.progress, event, expected_revision
            )
            if progress == current.progress:
                return current
            observed = isinstance(
                event, (CallCompleted, CallUncertain, AttemptCompleted, AttemptResolved)
            )
            if reconciling and not observed:
                raise OwnershipConflict(
                    "Reconciliation cannot register new construction work"
                )
            if not observed:
                candidate = ConstructionSnapshot(
                    capacity=self.capacity,
                    creation_operation=current.creation_operation,
                    progress=progress,
                )
            self.verifier.event(current.progress, event, op, control)
            if observed:
                retained = self.evidence.put(
                    event.model_dump_json().encode(),
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="construction-event/1",
                        visibility="private",
                        producer="construction-journal-v1",
                    ),
                    control=control,
                )
                control.checkpoint()
                candidate = ConstructionSnapshot(
                    capacity=self.capacity,
                    creation_operation=current.creation_operation,
                    progress=progress,
                )
            return candidate

        try:
            return self._transaction(op, update)
        except Exception as error:
            if retained is not None:
                raise ConstructionCommitUnconfirmed(retained) from error
            raise
