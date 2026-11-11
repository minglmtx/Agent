"""Public measured viewport from one capture; no hidden DOM or authority."""

from datetime import datetime
import hashlib
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .evidence import EvidenceMetadata, EvidenceRef
from .evidence_identity import evidence_reference
from .errors import EvidenceIntegrityError
from .identity import TaskIdentity
from .observation import Observation
from .validation import Contract, Identifier, Sha256

MAX_VIEWPORT_BYTES = 4 * 1024 * 1024
VIEWPORT_NAME = "public-viewport"
VIEWPORT_METADATA = EvidenceMetadata(
    content_schema="observation-viewport/1",
    media_type="application/json",
    visibility="public",
    producer="browsergym-public-viewport-v1",
)


class ViewportBox(Contract):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    width: float = Field(ge=0, allow_inf_nan=False)
    height: float = Field(ge=0, allow_inf_nan=False)


class ViewportElement(Contract):
    node_id: str = Field(min_length=1, max_length=128)
    visibility: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    box: ViewportBox | None = None


class ObservationViewport(Contract):
    schema_version: Literal["observation-viewport/1"] = "observation-viewport/1"
    observation_id: Identifier
    task: TaskIdentity
    context_id: Identifier
    attempt_id: Identifier
    sequence: int = Field(ge=0)
    captured_at: AwareDatetime
    tab_id: Identifier
    active_url: str
    text_sha256: Sha256
    coordinates: Literal["browsergym-scaled-viewport-pixels/1"] = (
        "browsergym-scaled-viewport-pixels/1"
    )
    width: int = Field(ge=1, le=32768)
    height: int = Field(ge=1, le=32768)
    elements: tuple[ViewportElement, ...] = Field(max_length=65536)

    @model_validator(mode="after")
    def bounded_unique(self) -> Self:
        ids = tuple(element.node_id for element in self.elements)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Viewport elements need unique canonical public node IDs")
        if len(self.model_dump_json().encode()) > MAX_VIEWPORT_BYTES:
            raise ValueError("Public viewport exceeds its explicit byte boundary")
        return self

    @property
    def reference(self) -> EvidenceRef:
        return evidence_reference(self.model_dump_json().encode(), VIEWPORT_METADATA)

    def require_observation(
        self, observed: Observation, text: str | None = None
    ) -> None:
        observed = Observation.model_validate(observed)
        if text is not None and observed.text is not None and text != observed.text:
            raise EvidenceIntegrityError(
                "Viewport resolution changed the inline public body"
            )
        body = observed.text if text is None else text
        active = next(
            (tab for tab in observed.tabs if tab.tab_id == observed.active_tab_id), None
        )
        if (
            active is None
            or body is None
            or (
                self.observation_id,
                self.task,
                self.context_id,
                self.attempt_id,
                self.sequence,
                self.captured_at,
                self.tab_id,
                self.active_url,
                self.text_sha256,
            )
            != (
                observed.observation_id,
                observed.task,
                observed.context_id,
                observed.attempt_id,
                observed.sequence,
                observed.captured_at,
                observed.active_tab_id,
                active.url,
                hashlib.sha256(body.encode()).hexdigest(),
            )
        ):
            raise EvidenceIntegrityError(
                "Viewport belongs to a different capture/tab/full text"
            )
        refs = tuple(a.reference for a in observed.artifacts if a.name == VIEWPORT_NAME)
        if refs != (self.reference,):
            raise EvidenceIntegrityError(
                "Observation lacks its exact public viewport artifact"
            )


def viewport_reference(observed: Observation) -> EvidenceRef | None:
    refs = tuple(a.reference for a in observed.artifacts if a.name == VIEWPORT_NAME)
    if not refs:
        return None  # Explicit legacy observation; not proof of measured visibility.
    if (
        len(refs) != 1
        or (
            refs[0].content_schema,
            refs[0].visibility,
            refs[0].media_type,
            refs[0].producer,
        )
        != (
            VIEWPORT_METADATA.content_schema,
            VIEWPORT_METADATA.visibility,
            VIEWPORT_METADATA.media_type,
            VIEWPORT_METADATA.producer,
        )
        or refs[0].size_bytes > MAX_VIEWPORT_BYTES
    ):
        raise EvidenceIntegrityError("Invalid or oversized public viewport reference")
    return refs[0]
