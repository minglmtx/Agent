"""Readable full field/body-sharing format; pages carry no business identity."""

from typing import Literal, Self
from pydantic import Field, JsonValue, field_validator, model_validator
from .validation import Contract
from .teacher_json import MAX_TEACHER_BYTES, json_value

TEACHER_VIEW_VERSION = "teacher-required-evidence-projection-v2"


class TeacherSharedPage(Contract):
    page_id: str = Field(pattern=r"^p(?:0|[1-9][0-9]*)$")
    text: str


class TeacherProjectionPayload(Contract):
    version: Literal["teacher-required-evidence-projection-v2"] = (
        "teacher-required-evidence-projection-v2"
    )
    field_projection: Literal[True] = True
    archival_byte_reversible: Literal[False] = False
    observation_protocol: dict[str, JsonValue]
    pages: tuple[TeacherSharedPage, ...] = Field(min_length=1, max_length=100000)
    evidence: dict[str, JsonValue]

    @field_validator("field_projection", "archival_byte_reversible", mode="before")
    @classmethod
    def actual_flags(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Exact Teacher format booleans required")
        return value

    @model_validator(mode="after")
    def complete_payload(self) -> Self:
        json_value(self.observation_protocol)
        json_value(self.evidence)
        if len({p.page_id for p in self.pages}) != len(self.pages):
            raise ValueError("Unique shared page IDs required")
        if len(self.model_dump_json().encode()) > MAX_TEACHER_BYTES:
            raise ValueError("Complete Teacher projection exceeds byte bound")
        return self
