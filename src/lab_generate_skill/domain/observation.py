"""Public browser facts; capture success is not baseline or task success.

The producer reports the actual browser context/attempt and sequence. A ready
empty page is representable; missing/loading/error observations remain explicit.
Only public artifacts are allowed. Text is preserved without trimming or summary.
"""

import hashlib
from datetime import datetime, timezone
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .evidence import EvidenceRef
from .identity import TaskIdentity
from .validation import Contract, Identifier, NonEmptyText


class BrowserTab(Contract):
    tab_id: Identifier
    url: NonEmptyText
    title: str

    @field_validator("title")
    @classmethod
    def utf8_title(cls, value: str) -> str:
        value.encode("utf-8")
        return value

    @field_validator("url")
    @classmethod
    def observed_url(cls, value: str) -> str:
        value.encode("utf-8")
        parsed = urlsplit(value)
        if (
            not parsed.scheme
            or parsed.username is not None
            or parsed.password is not None
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError(
                "Observed URL needs a scheme and no credentials or control characters"
            )
        if parsed.scheme in ("http", "https") and not parsed.hostname:
            raise ValueError("Observed HTTP URL needs a host")
        return value


class ObservationArtifact(Contract):
    name: Identifier
    reference: EvidenceRef

    @model_validator(mode="after")
    def public(self) -> Self:
        if self.reference.visibility != "public":
            raise ValueError("Observation artifacts must be public")
        return self


class Observation(Contract):
    schema_version: Literal["observation/1"] = "observation/1"
    observation_id: Identifier
    task: TaskIdentity
    context_id: Identifier
    attempt_id: Identifier
    sequence: int = Field(ge=0)
    captured_at: AwareDatetime
    tabs: tuple[BrowserTab, ...]
    active_tab_id: Identifier | None
    state: Literal["ready", "loading", "error", "unavailable"]
    error_code: Identifier | None = None
    text: str | None = None
    text_ref: EvidenceRef | None = None
    artifacts: tuple[ObservationArtifact, ...] = ()
    last_action_error: str = ""

    @field_validator("text", "last_action_error")
    @classmethod
    def exact_utf8(cls, value: str | None) -> str | None:
        if value is not None:
            value.encode("utf-8")
        return value

    @field_validator("captured_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def consistent_public_facts(self) -> Self:
        ids = [tab.tab_id for tab in self.tabs]
        if len(ids) != len(set(ids)) or len({a.name for a in self.artifacts}) != len(
            self.artifacts
        ):
            raise ValueError("Tab IDs and artifact names must be unique")
        if self.tabs:
            if self.active_tab_id not in ids:
                raise ValueError("Active tab must exist in observed tabs")
        elif self.active_tab_id is not None or self.state not in (
            "error",
            "unavailable",
        ):
            raise ValueError(
                "No tabs requires an explicit failed/unavailable observation"
            )
        if (self.state in ("error", "unavailable")) != (self.error_code is not None):
            raise ValueError("Observation failure state requires its explicit reason")
        if self.text is not None and self.text_ref is not None:
            raise ValueError(
                "Choose inline text or referenced text, not two competing bodies"
            )
        if self.text_ref is not None and (
            self.text_ref.visibility != "public"
            or self.text_ref.content_schema != "observation-text/1"
        ):
            raise ValueError("Referenced text must be public observation-text/1 UTF-8")
        if (
            self.state == "ready"
            and self.text is None
            and self.text_ref is None
            and not self.artifacts
        ):
            raise ValueError(
                "Ready observation requires actual content, even explicit empty text"
            )
        return self

    def check_initial(self, task: TaskIdentity, context_id: str) -> None:
        """Structural initial-view gate, not environment/closure qualification."""
        Observation.model_validate(self)
        task = TaskIdentity.model_validate(task)
        if self.task != task or self.context_id != context_id or self.sequence != 0:
            raise ValueError(
                "Initial observation must match task/context and sequence zero"
            )
        if self.state != "ready" or self.last_action_error:
            raise ValueError(
                "Initial observation cannot be loading, missing or carry an action error"
            )


class ResolvedObservation(Contract):
    """Original record plus exact resolved text; artifact references stay intact."""

    record: Observation
    text: str | None

    @model_validator(mode="after")
    def exact_text(self) -> Self:
        if self.record.text_ref is None:
            if self.text != self.record.text:
                raise ValueError("Resolved inline text differs from original")
        else:
            if self.text is None:
                raise ValueError("Referenced text must be resolved")
            raw = self.text.encode("utf-8")
            if (
                len(raw) != self.record.text_ref.size_bytes
                or hashlib.sha256(raw).hexdigest() != self.record.text_ref.sha256
            ):
                raise ValueError("Resolved text differs from referenced UTF-8 bytes")
        return self


class ObservationCommitUnconfirmed(RuntimeError):
    """Publication returned a known reference but its final checkpoint failed."""

    reason_code = "OBSERVATION_COMMIT_UNCONFIRMED"

    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        super().__init__(
            "Observation persisted; reconcile the existing reference, do not recapture"
        )
