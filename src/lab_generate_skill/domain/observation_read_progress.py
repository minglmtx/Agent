"""Pure same-observation window facts, derived by the existing Actor trace.

No persistent ledger, source/dispatch permit, cached current authority or saved
body history. Only one active body reference and bounded structured read records.
"""

import hashlib
import json
from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .actor_versions import actor_version_fields, actor_version_output
from .observation_read import ObservationSourceSpan
from .observation_read_geometry import ObservationProgressKind, ranges_already_displayed
from .context_budget import CountedContextInput
from .evidence import EvidenceRef
from .errors import EvidenceIntegrityError, OwnershipConflict
from .observation_read import ObservationReadRequest, PublicObservationSnapshot
from .observation_read_policy import ObservationReadPolicy
from .validation import Contract, Sha256


def observation_request_key(request: ObservationReadRequest) -> str:
    # Full snapshot/scope/tab/frame/policy, range/cursor/query/mode and output
    # options participate. A fresh logical request ID cannot reset a quota.
    data = request.model_dump(mode="json", exclude={"request_id"})
    return hashlib.sha256(
        json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class ObservationReadRecord(Contract):
    request: ObservationReadRequest
    result_ref: EvidenceRef
    body_sha256: Sha256
    count: CountedContextInput
    displayed_spans: tuple[ObservationSourceSpan, ...] | None = Field(
        default=None, max_length=2048
    )
    progress_kind: ObservationProgressKind | None = None
    progress_fingerprint: Sha256 | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.result_ref.content_schema == "observation-read-result/1",
            ("displayed_spans", "progress_kind", "progress_fingerprint"),
        )

    @model_validator(mode="after")
    def original_public_result_and_exact_count(self) -> Self:
        old = self.result_ref.content_schema == "observation-read-result/1"
        actor_version_fields(
            self,
            old,
            ("displayed_spans", "progress_kind", "progress_fingerprint"),
            record_name="Read record",
        )
        if not old and (
            self.displayed_spans is None
            or self.progress_kind is None
            or self.progress_fingerprint is None
        ):
            raise ValueError(
                "Current read result requires actual displayed coordinates and semantic coverage facts"
            )
        if (
            self.result_ref.visibility != "public"
            or self.result_ref.content_schema
            not in ("observation-read-result/1", "observation-read-result/2")
            or self.result_ref.media_type != "application/json"
        ):
            raise ValueError("Original public read result required")
        measurement = self.count.measurement
        if (
            measurement.role != "actor"
            or measurement.precision != "exact"
            or (
                measurement.observation_tokens is None
                or measurement.observation_body_sha256 != self.body_sha256
            )
        ):
            raise ValueError(
                "Exact original local-body count required; no fragment estimate"
            )
        return self


class ObservationReadProgress(Contract):
    schema_version: Literal[
        "observation-read-progress/1", "observation-read-progress/2"
    ] = "observation-read-progress/1"
    snapshot: PublicObservationSnapshot
    policy: ObservationReadPolicy
    records: tuple[ObservationReadRecord, ...] = Field(max_length=64)
    no_progress: int = Field(ge=0, le=64)
    initial_displayed_spans: tuple[ObservationSourceSpan, ...] | None = Field(
        default=None, max_length=2048
    )
    initial_progress_fingerprint: Sha256 | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "observation-read-progress/1",
            ("initial_displayed_spans", "initial_progress_fingerprint"),
        )

    def _unchanged(
        self, record: ObservationReadRecord, previous: ObservationReadRecord | None
    ) -> bool:
        if record.displayed_spans is not None:
            spans = (
                self.initial_displayed_spans
                if previous is None
                else previous.displayed_spans
            )
            fingerprint = (
                self.initial_progress_fingerprint
                if previous is None
                else previous.progress_fingerprint
            )
            if record.progress_kind == "content_ranges" and spans is not None:
                return ranges_already_displayed(spans, record.displayed_spans)
            if record.progress_fingerprint is not None and fingerprint is not None:
                return record.progress_fingerprint == fingerprint
        return previous is not None and previous.body_sha256 == record.body_sha256

    @model_validator(mode="after")
    def original_observation_and_window(self) -> Self:
        old = self.schema_version == "observation-read-progress/1"
        actor_version_fields(
            self,
            old,
            ("initial_displayed_spans", "initial_progress_fingerprint"),
            record_name="Read progress",
        )
        if not old and self.initial_displayed_spans is None:
            raise ValueError(
                "Actual reading progress requires the first model's displayed source coordinates"
            )
        if (
            self.snapshot.policy_sha256 != self.policy.digest
            or len(self.records) > self.policy.reads_per_observation
        ):
            raise ValueError("Original frozen snapshot and shared read quota required")
        if self.no_progress > len(self.records):
            raise ValueError("No-progress count exceeds actual accepted read records")
        no_progress = 0
        previous: ObservationReadRecord | None = None
        ids: set[str] = set()
        original_bodies: dict[str, str] = {}
        for record in self.records:
            if no_progress >= self.policy.consecutive_no_progress:
                raise ValueError(
                    "Read history continued after its controlled no-progress stop"
                )
            if (
                record.request.snapshot != self.snapshot
                or record.request.request_id in ids
            ):
                raise OwnershipConflict(
                    "Read history changed snapshot or reused request identity"
                )
            ids.add(record.request.request_id)
            tokens = record.count.measurement.observation_tokens
            if (
                tokens is None
                or tokens > self.policy.body_max_tokens
                or tokens > record.request.output_tokens
            ):
                raise ValueError("Actual returned body exceeds its shared token budget")
            key = observation_request_key(record.request)
            if key in original_bodies and original_bodies[key] != record.body_sha256:
                raise EvidenceIntegrityError(
                    "Identical same-snapshot reading changed immutable body"
                )
            original_bodies[key] = record.body_sha256
            no_progress = no_progress + 1 if self._unchanged(record, previous) else 0
            previous = record
        if no_progress != self.no_progress:
            raise ValueError(
                "Progress must derive from actual active-body facts, not model understanding"
            )
        return self

    @property
    def reads_used(self) -> int:
        return len(self.records)

    @property
    def remaining(self) -> int:
        return self.policy.reads_per_observation - self.reads_used

    @property
    def warn_remaining(self) -> bool:
        return self.remaining == self.policy.warn_remaining

    @property
    def active(self) -> ObservationReadRecord | None:
        return self.records[-1] if self.records else None

    @property
    def controlled_stop(self) -> Literal["read_no_progress"] | None:
        return (
            "read_no_progress"
            if self.no_progress >= self.policy.consecutive_no_progress
            else None
        )

    def require_read(self, request: ObservationReadRequest) -> None:
        if request.snapshot != self.snapshot:
            raise OwnershipConflict(
                "Old snapshot/cursor cannot become current observation"
            )
        if self.remaining <= 0 or self.controlled_stop is not None:
            raise ValueError(
                "Controlled observation reading stop; no forced website action or task failure"
            )
        if any(
            record.request.request_id == request.request_id for record in self.records
        ):
            raise OwnershipConflict(
                "Original read request already returned; no redispatch"
            )
        if request.output_tokens > self.policy.body_max_tokens:
            raise ValueError("Read options exceed frozen shared body limit")

    def identical_active(
        self, request: ObservationReadRequest
    ) -> ObservationReadRecord | None:
        self.require_read(request)
        current = self.active
        return (
            current
            if current is not None
            and observation_request_key(current.request)
            == observation_request_key(request)
            else None
        )

    def returned(self, record: ObservationReadRecord) -> "ObservationReadProgress":
        record = ObservationReadRecord.model_validate(record)
        self.require_read(record.request)
        current = self.active
        unchanged = self._unchanged(record, current)
        fields: dict[str, object] = {}
        if self.schema_version == "observation-read-progress/2":
            fields.update(
                schema_version=self.schema_version,
                initial_displayed_spans=self.initial_displayed_spans,
                initial_progress_fingerprint=self.initial_progress_fingerprint,
            )
        return ObservationReadProgress.model_validate(
            dict(
                snapshot=self.snapshot,
                policy=self.policy,
                records=(*self.records, record),
                no_progress=self.no_progress + 1 if unchanged else 0,
            )
            | fields
        )
