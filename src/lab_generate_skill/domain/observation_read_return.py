"""A known returned reading and its count facts, never permission to replay."""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .context_budget import CountedContextInput
from .evidence import EvidenceRef
from .observation_read import ObservationReadPayload
from .observation_read_progress import ObservationReadRecord
from .observation_read_geometry import (
    reading_display_spans,
    reading_progress_kind,
    reading_progress_fingerprint,
)
from .validation import Contract


class ReturnedObservationRead(Contract):
    schema_version: Literal["returned-observation-read/1"] = (
        "returned-observation-read/1"
    )
    result_ref: EvidenceRef
    payload: ObservationReadPayload
    body: str
    count: CountedContextInput

    @property
    def record(self) -> ObservationReadRecord:
        fields: dict[str, object] = {}
        if self.payload.schema_version == "observation-read-result/2":
            fields.update(
                displayed_spans=reading_display_spans(self.payload),
                progress_kind=reading_progress_kind(self.payload),
                progress_fingerprint=reading_progress_fingerprint(self.payload),
            )
        return ObservationReadRecord.model_validate(
            dict(
                request=self.payload.request,
                result_ref=self.result_ref,
                body_sha256=hashlib.sha256(self.body.encode()).hexdigest(),
                count=self.count,
            )
            | fields
        )

    @model_validator(mode="after")
    def exact_returned_body(self) -> Self:
        raw = self.payload.model_dump_json().encode()
        if self.result_ref.content_schema != self.payload.schema_version:
            raise ValueError(
                "Returned read reference changed its explicit result version"
            )
        if (self.result_ref.sha256, self.result_ref.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise ValueError(
                "Returned reading differs from its original public reference"
            )
        self.record
        return self


class ObservationReadCapacityBlocked(ValueError):
    """Necessary complete context cannot fit; not a negative business judgment."""


class ObservationReadUnconfirmed(RuntimeError):
    """Keep the original known return; no automatic count/read/publication replay."""

    def __init__(
        self,
        payload: ObservationReadPayload,
        body: str,
        count: CountedContextInput,
        result_ref: EvidenceRef | None,
        primary: BaseException,
    ) -> None:
        self.payload, self.body, self.count = payload, body, count
        self.result_ref, self.primary = result_ref, primary
        super().__init__(
            "Observation reading returned; publication or current gate unconfirmed"
        )
