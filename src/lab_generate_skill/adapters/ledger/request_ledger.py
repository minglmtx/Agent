"""One shared authorization transaction; no model call or permissive authority.

All runs/subbudgets use one stable lock and snapshot per authorization_id in the
same configured root. Dispatch returns a permit only after write/fsync AND lock
cleanup succeed. Lost acknowledgement never yields a second permit. Authority
is mandatory and independently verifies real permissions, claims and proofs.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from lab_generate_skill.domain.budget import BudgetAuthorization, BudgetScope, Money
from lab_generate_skill.domain.budget_policy import (
    BudgetDispatchPolicy,
    unsettled_dispatches,
)
from lab_generate_skill.domain.budget_journal import (
    BudgetJournalCapacity,
    BudgetJournalSnapshot,
    BudgetReconciliationRequired,
    SettlementPending,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    JournalCapacityExceeded,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.generation import (
    DispatchPermit,
    OutcomeProof,
    RequestIdentity,
    RequestReceipt,
    RequestRecord,
    Reservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.request_ledger import (
    BudgetSnapshot,
    dispatch_request,
    reserve_request,
    settle_request,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.requests import RequestAuthority

from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)

T = TypeVar("T")


class FileRequestLedger:
    def __init__(
        self,
        root: Path,
        authorization: BudgetAuthorization,
        capacity: BudgetJournalCapacity,
        controls: OperationControls,
        evidence: EvidenceStore,
        authority: RequestAuthority,
        *,
        dispatch_policy: BudgetDispatchPolicy,
    ) -> None:
        self._authorization = BudgetAuthorization.model_validate(authorization)
        self._capacity = BudgetJournalCapacity.model_validate(capacity)
        self._dispatch_policy = BudgetDispatchPolicy.model_validate(dispatch_policy)
        self._controls, self._evidence, self._authority = controls, evidence, authority
        empty = BudgetJournalSnapshot(
            capacity=self._capacity,
            dispatch_policy=self._dispatch_policy,
            history=BudgetSnapshot(authorization=self._authorization),
        )
        empty.check_capacity()
        self._file = AtomicSnapshotFile(
            root,
            hashlib.sha256(authorization.authorization_id.encode()).hexdigest()
            + ".requests.json",
            max_bytes=self._capacity.max_bytes,
        )

    def _guard(
        self, request: RequestIdentity, op: OperationContext
    ) -> OperationControl:
        if request.authorization_id != self._authorization.authorization_id or (
            op.run_id,
            op.owner_id,
            op.attempt_id,
        ) != (request.owner.run_id, request.owner.owner_id, request.attempt_id):
            raise OwnershipConflict(
                "Request operation must retain authorization and original scope"
            )
        control = self._controls.bind(op)
        control.checkpoint()
        return control

    def _refs(self, refs: tuple[EvidenceRef, ...], control: OperationControl) -> None:
        for ref in dict.fromkeys(refs):
            control.checkpoint()
            self._evidence.read(ref, control=control)
            control.checkpoint()

    def _load(self, raw: bytes | None) -> BudgetJournalSnapshot:
        if raw is None:
            return BudgetJournalSnapshot(
                capacity=self._capacity,
                dispatch_policy=self._dispatch_policy,
                history=BudgetSnapshot(authorization=self._authorization),
            )
        try:
            value = BudgetJournalSnapshot.model_validate_json(raw)
            value.check_capacity()
        except (ValidationError, JournalCapacityExceeded) as error:
            raise EvidenceIntegrityError(
                "Invalid budget journal history or capacity"
            ) from error
        if (
            value.history.authorization != self._authorization
            or value.capacity != self._capacity
            or value.dispatch_policy != self._dispatch_policy
        ):
            raise OwnershipConflict(
                "Shared authorization or journal capacity cannot change"
            )
        return value

    def _transaction(
        self,
        request: RequestIdentity,
        op: OperationContext,
        update: Callable[
            [BudgetJournalSnapshot, OperationControl, SnapshotTransaction],
            tuple[BudgetSnapshot, T],
        ],
        after_commit: Callable[[SnapshotTransaction], None] | None = None,
    ) -> T:
        control = self._guard(request, op)
        with self._file.locked(control) as file:
            current = self._load(file.read())
            history, result = update(current, control, file)
            if history != current.history:
                candidate = BudgetJournalSnapshot(
                    capacity=self._capacity,
                    dispatch_policy=self._dispatch_policy,
                    history=history,
                    operations=(*current.operations, op),
                )
                candidate.check_capacity()
                file.write(candidate.model_dump_json().encode())
            if after_commit is not None:
                after_commit(file)
            file.checkpoint()
        # Do not return a permit until descriptor/lock cleanup also succeeded.
        return result

    @staticmethod
    def _record(history: BudgetSnapshot, request: RequestIdentity) -> RequestRecord:
        for record in history.project():
            if record.reservation.request.request_id == request.request_id:
                if record.reservation.request != request:
                    raise OwnershipConflict("Request identity is frozen")
                return record
        raise EvidenceNotFound("Request has no committed reservation")

    def reserve(
        self,
        scope: BudgetScope,
        request: RequestIdentity,
        ceiling: Money,
        op: OperationContext,
    ) -> Reservation:
        scope, request = BudgetScope.model_validate(
            scope
        ), RequestIdentity.model_validate(request)
        ceiling, op = Money.model_validate(ceiling), OperationContext.model_validate(op)
        if op.mode != "execute":
            raise OwnershipConflict("Cleanup cannot reserve paid requests")

        def update(
            current: BudgetJournalSnapshot,
            control: OperationControl,
            file: SnapshotTransaction,
        ) -> tuple[BudgetSnapshot, Reservation]:
            result, reservation = reserve_request(
                current.history, scope, request, ceiling, op.operation_id
            )
            if result != current.history:
                pending = unsettled_dispatches(current.history)
                if pending:
                    raise BudgetReconciliationRequired(
                        "Unsettled dispatch blocks new shared spending", pending
                    )
                if file.pending_keys():
                    raise BudgetReconciliationRequired(
                        "Unconfirmed settlement blocks new reservations"
                    )
                self._refs((self._authorization.authorization_ref,), control)
                self._authority.authorize_reservation(reservation, op)
                control.checkpoint()
            return result, reservation

        return self._transaction(request, op, update)

    def mark_dispatching(
        self, reservation: Reservation, expected_revision: int, op: OperationContext
    ) -> DispatchPermit:
        reservation, op = Reservation.model_validate(
            reservation
        ), OperationContext.model_validate(op)
        if op.mode != "execute":
            raise OwnershipConflict("Cleanup cannot dispatch paid requests")

        def update(
            current: BudgetJournalSnapshot,
            control: OperationControl,
            file: SnapshotTransaction,
        ) -> tuple[BudgetSnapshot, DispatchPermit]:
            history = dispatch_request(
                current.history, reservation, expected_revision, op.operation_id
            )
            pending = unsettled_dispatches(current.history)
            if pending:
                raise BudgetReconciliationRequired(
                    "Unsettled dispatch blocks new shared spending", pending
                )
            if file.pending_keys():
                raise BudgetReconciliationRequired(
                    "Unconfirmed settlement blocks new sends"
                )
            before = self._record(current.history, reservation.request)
            self._refs((self._authorization.authorization_ref,), control)
            self._authority.authorize_dispatch(before, op)
            control.checkpoint()
            permit = DispatchPermit(
                request=reservation.request,
                dispatch_operation_id=op.operation_id,
                request_revision=self._record(history, reservation.request).revision,
            )
            return history, permit

        return self._transaction(reservation.request, op, update)

    def settle(
        self,
        request: RequestIdentity,
        proof: OutcomeProof,
        expected_revision: int,
        op: OperationContext,
    ) -> RequestReceipt:
        request, proof = RequestIdentity.model_validate(
            request
        ), OutcomeProof.model_validate(proof)
        op = OperationContext.model_validate(op)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected request revision must be a nonnegative integer")
        if proof.request != request:
            raise OwnershipConflict("Proof must preserve the complete request identity")
        if proof.outcome == "released_not_dispatched" and op.mode != "cleanup":
            raise OwnershipConflict("Undispatched release requires cleanup scope")
        retained: EvidenceRef | None = None

        def update(
            current: BudgetJournalSnapshot,
            control: OperationControl,
            file: SnapshotTransaction,
        ) -> tuple[BudgetSnapshot, RequestReceipt]:
            nonlocal retained
            record = self._record(current.history, request)
            replay = any(
                event.proof is not None and event.proof.digest == proof.digest
                for event in record.events
            )
            if not replay:
                if record.revision != expected_revision:
                    raise RevisionConflict("Request revision changed before settlement")
                refs = proof.evidence
                if proof.response_ref is not None:
                    refs += (proof.response_ref,)
                if proof.writer_termination_ref is not None:
                    refs += (proof.writer_termination_ref,)
                self._refs(refs, control)
                self._authority.verify_outcome(record, proof, op)
                control.checkpoint()
                canonical = json.dumps(
                    proof.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
                retained = self._evidence.put(
                    canonical,
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="request-outcome/2",
                        visibility="private",
                        producer="request-ledger-v2",
                    ),
                    control=control,
                )
                control.checkpoint()
                # Unknown evidence changes neither charge nor held amount. A
                # failed unknown observation keeps the original reservation;
                # verified monetary/non-execution facts must fence all senders.
                if proof.outcome != "uncertain":
                    file.retain_pending(
                        proof.digest, retained.model_dump_json().encode()
                    )
            return settle_request(
                current.history, request, proof, expected_revision, op.operation_id
            )

        def committed(file: SnapshotTransaction) -> None:
            nonlocal retained
            raw = file.pending(proof.digest)
            if raw is None:
                return
            try:
                retained = EvidenceRef.model_validate_json(raw)
            except ValidationError as error:
                raise EvidenceIntegrityError(
                    "Malformed pending settlement reference"
                ) from error
            if (
                retained.sha256 != proof.digest
                or retained.content_schema != "request-outcome/2"
                or retained.visibility != "private"
            ):
                raise EvidenceIntegrityError(
                    "Pending marker differs from the committed proof"
                )
            self._evidence.read(retained, control=self._guard(request, op))
            file.checkpoint()
            file.resolve_pending(proof.digest, raw)

        try:
            return self._transaction(request, op, update, committed)
        except Exception as error:
            if retained is not None:
                raise SettlementPending(retained) from error
            raise

    def read(self, request: RequestIdentity, op: OperationContext) -> RequestRecord:
        request, op = RequestIdentity.model_validate(
            request
        ), OperationContext.model_validate(op)

        def inspect(
            current: BudgetJournalSnapshot,
            control: OperationControl,
            file: SnapshotTransaction,
        ) -> tuple[BudgetSnapshot, RequestRecord]:
            return current.history, self._record(current.history, request)

        return self._transaction(request, op, inspect)
