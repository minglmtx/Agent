"""One original Actor's immutable snapshot reader; no browser or second journal.

The caller supplies progress freshly derived from the original Actor trace. This
adapter holds one current returned body, an immutable source/index and opaque
cursor capabilities; it grants no cross-attempt or cross-process continuation.
"""

from dataclasses import dataclass
import hashlib
import hmac
import os
import secrets
import threading
from pydantic import TypeAdapter
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation_read import (
    ObservationReadRequest,
    ListObservationRegions,
    SearchObservationRegions,
)
from lab_generate_skill.domain.observation_read_progress import (
    ObservationReadProgress,
    observation_request_key,
)
from lab_generate_skill.domain.observation_read_return import (
    ReturnedObservationRead,
    ObservationReadCapacityBlocked,
    ObservationReadUnconfirmed,
)
from lab_generate_skill.policies.observation_index import ObservationIndex
from lab_generate_skill.policies.observation_pages import (
    ObservationPage,
    observation_page,
)
from lab_generate_skill.policies.observation_search import (
    ObservationSearchIndex,
    index_literal_search,
)
from lab_generate_skill.domain.context_budget import CountedContextInput
from lab_generate_skill.policies.observation_display import observation_read_body
from lab_generate_skill.policies.observation_proposals import (
    check_indexed_proposal,
    check_issued_continuation,
)
from lab_generate_skill.policies.actor_proposal_feedback import reject_proposal
from lab_generate_skill.ports.observation_reads import (
    ObservationReadAuthority,
    ObservationBodyCounts,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl

_REQUEST: TypeAdapter[ObservationReadRequest] = TypeAdapter(ObservationReadRequest)
_METADATA = EvidenceMetadata(
    media_type="application/json",
    content_schema="observation-read-result/1",
    visibility="public",
    producer="original-actor-observation-reader-v1",
)


def _cursor_binding(request: ObservationReadRequest) -> str:
    return observation_request_key(request.model_copy(update={"continuation": None}))


@dataclass(frozen=True)
class _Cursor:
    binding: str
    offset: int


class SnapshotObservationReads:
    def __init__(
        self,
        index: ObservationIndex,
        evidence: EvidenceStore,
        authority: ObservationReadAuthority,
        counts: ObservationBodyCounts,
    ) -> None:
        self._index: ObservationIndex | None = index
        self._search: ObservationSearchIndex | None = index_literal_search(index)
        self._cursor_secret = secrets.token_bytes(32)
        self._evidence, self._authority, self._counts = evidence, authority, counts
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._cursors: dict[str, _Cursor] = {}
        self._spent: set[str] = set()
        self._active: ReturnedObservationRead | None = None
        self._busy = False
        self._closed = False

    def close(self) -> None:
        self._require_local()
        self._closed = True
        self._index = None
        self._search = None
        self._active = None
        self._cursors.clear()

    def _require_local(self) -> None:
        if (os.getpid(), threading.get_ident()) != (self._pid, self._thread):
            raise OwnershipConflict(
                "Original observation reader cannot cross process or thread"
            )

    def automatic_directory(
        self,
        request: ListObservationRegions,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> ObservationPage:
        """Pure initial candidate/cursor; no Actor read, count, publication or quota."""
        self._require_local()
        if self._closed or self._index is None or self._search is None or self._spent:
            raise OwnershipConflict(
                "Automatic directory requires this fresh original snapshot"
            )
        self._index.require_snapshot(request.snapshot)
        self._authority.require_current(request.snapshot, operation, control=control)
        cursor = (
            "read-"
            + hmac.new(
                self._cursor_secret,
                observation_request_key(request).encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
        )
        page = observation_page(
            self._index,
            request,
            offset=0,
            limit=self._index.policy.directory_entries,
            next_cursor=cursor,
            search=self._search,
        )
        if page.next_offset is not None:
            self._cursors[cursor] = _Cursor(_cursor_binding(request), page.next_offset)
        return page

    @property
    def active_return(self) -> ReturnedObservationRead | None:
        self._require_local()
        return self._active

    def check_proposal(
        self,
        request: ObservationReadRequest,
        *,
        progress: ObservationReadProgress,
        control: OperationControl,
    ) -> None:
        self._require_local()
        control.checkpoint()
        index = self._index
        if self._closed or self._busy or index is None:
            raise OwnershipConflict(
                "Original reading preflight has no live retained reader"
            )
        request = _REQUEST.validate_python(request)
        progress = ObservationReadProgress.model_validate(progress)
        index.require_snapshot(request.snapshot)
        if (progress.snapshot, progress.policy) != (index.snapshot, index.policy):
            raise OwnershipConflict(
                "Reading preflight changed original progress/source"
            )
        if request.request_id in self._spent:
            raise OwnershipConflict(
                "This read was already attempted; preflight grants no redispatch"
            )
        if (self._active is None and progress.records) or (
            self._active is not None and progress.active != self._active.record
        ):
            raise OwnershipConflict(
                "Original reader cannot recover cursor/body ownership from recorded history"
            )
        if progress.remaining <= 0:
            reject_proposal(
                "READ_QUOTA_EXHAUSTED",
                "No reads remain for this public snapshot.",
                "Use already displayed evidence or task-relevant browser controls; do not claim a site-wide search.",
                tool=request.tool,
                actual=progress.remaining,
                allowed=0,
            )
        progress.require_read(
            request
        )  # Other stopped/invalid progress remains an engineering failure.
        check_indexed_proposal(index, request)
        check_issued_continuation(
            request, {key: value.binding for key, value in self._cursors.items()}
        )
        control.checkpoint()

    def read(
        self,
        request: ObservationReadRequest,
        operation: OperationContext,
        *,
        progress: ObservationReadProgress,
        control: OperationControl,
        retention_control: OperationControl | None = None,
    ) -> ReturnedObservationRead:
        self._require_local()
        if self._closed or self._busy or self._index is None:
            raise OwnershipConflict(
                "Original observation reading lifetime is closed or busy"
            )
        request = _REQUEST.validate_python(request)
        operation = OperationContext.model_validate(operation)
        progress = ObservationReadProgress.model_validate(progress)
        index = self._index
        index.require_snapshot(request.snapshot)
        if progress.snapshot != index.snapshot or progress.policy != index.policy:
            raise OwnershipConflict("Reading changed original frozen progress/source")
        progress.require_read(request)
        if request.request_id in self._spent:
            raise OwnershipConflict(
                "Original reading was already attempted; no automatic redispatch"
            )
        if (self._active is None and progress.records) or (
            self._active is not None
            and (progress.active is None or progress.active != self._active.record)
        ):
            raise OwnershipConflict(
                "Reading progress is not this original Actor's returned trace"
            )
        offset = 0
        if request.continuation is not None:
            cursor = self._cursors.get(request.continuation)
            if cursor is None or cursor.binding != _cursor_binding(request):
                raise OwnershipConflict(
                    "Unknown, altered or foreign original read cursor"
                )
            offset = cursor.offset
        control.checkpoint()
        self._authority.require_current(index.snapshot, operation, control=control)
        self._busy = True
        self._spent.add(request.request_id)
        result_control = retention_control if retention_control is not None else control
        try:
            if progress.identical_active(request) is not None:
                assert self._active is not None
                payload = self._active.payload.model_copy(update={"request": request})
                body = observation_read_body(payload)
                if body != self._active.body:
                    raise EvidenceIntegrityError(
                        "Identical displayed reading changed its actual body"
                    )
                count = self._active.count
                page = ObservationPage(payload, None)
            else:
                next_cursor = (
                    "read-"
                    + hmac.new(
                        self._cursor_secret,
                        observation_request_key(request).encode(),
                        hashlib.sha256,
                    ).hexdigest()[:32]
                )
                assert self._search is not None
                limit = (
                    index.policy.directory_entries
                    if isinstance(request, ListObservationRegions)
                    else (
                        min(index.policy.search_hits, index.policy.max_ranges)
                        if isinstance(request, SearchObservationRegions)
                        else index.policy.page_units
                    )
                )
                while True:
                    control.checkpoint()
                    page = observation_page(
                        index,
                        request,
                        offset=offset,
                        limit=limit,
                        next_cursor=next_cursor,
                        search=self._search,
                    )
                    payload = page.payload
                    body = observation_read_body(payload)
                    self._authority.require_current(
                        index.snapshot, operation, control=control
                    )
                    count = CountedContextInput.model_validate(
                        self._counts.measure_body(
                            payload,
                            body,
                            operation,
                            control=control,
                            retention_control=retention_control,
                        )
                    )
                    measured = count.measurement
                    if (
                        measured.role != "actor"
                        or measured.precision != "exact"
                        or measured.observation_tokens is None
                        or measured.observation_body_sha256
                        != hashlib.sha256(body.encode()).hexdigest()
                    ):
                        raise EvidenceIntegrityError(
                            "Original native counter did not count this complete reading body"
                        )
                    if measured.observation_tokens <= min(
                        request.output_tokens, index.policy.body_max_tokens
                    ):
                        break
                    if limit == 1:
                        raise ObservationReadCapacityBlocked(
                            "Necessary complete source unit/context exceeds reading capacity; no silent truncation or forced action"
                        )
                    limit = max(1, limit // 2)
            result_ref: EvidenceRef | None = None
            try:
                # Keep the original pre-publication current gate. A known body
                # can still be retained under cleanup when execution expires;
                # that failed gate never authorizes an active reading window.
                gate_error: BaseException | None = None
                try:
                    self._authority.require_current(
                        index.snapshot, operation, control=control
                    )
                except BaseException as error:
                    if retention_control is None:
                        raise
                    gate_error = error
                raw = payload.model_dump_json().encode()
                result_ref = self._evidence.put(
                    raw,
                    _METADATA.model_copy(
                        update={"content_schema": payload.schema_version}
                    ),
                    result_control,
                )
                returned = ReturnedObservationRead(
                    result_ref=result_ref, payload=payload, body=body, count=count
                )
                progress.returned(returned.record)
                if gate_error is not None:
                    raise gate_error
                self._authority.require_current(
                    index.snapshot, operation, control=control
                )
                control.checkpoint()
            except BaseException as error:
                raise ObservationReadUnconfirmed(
                    payload, body, count, result_ref, error
                ) from error
            if page.next_offset is not None:
                assert payload.continuation is not None
                if (
                    payload.continuation not in self._cursors
                    and len(self._cursors) >= index.policy.reads_per_observation + 1
                ):
                    raise OwnershipConflict(
                        "Original bounded cursor capacity exhausted"
                    )
                self._cursors[payload.continuation] = _Cursor(
                    _cursor_binding(request), page.next_offset
                )
            self._active = returned
            return returned
        except BaseException:
            # The original returned evidence/exception survives. A fresh reader
            # cannot take over its history, and the same ID cannot count again.
            self._closed = True
            raise
        finally:
            self._busy = False
