"""Versioned public skill content; bank lineage/qualification is separate.

The model payload remains exactly three stripped strings. content_digest uses
the existing UTF-8 sorted-key JSON fingerprint, excluding the envelope schema;
it is a deduplication identity, not a CAS payload digest or admission proof.
"""

import hashlib
import json
from typing import Literal, Self

from pydantic import field_validator, model_validator

from .skill_limits import validate_skill
from .validation import Contract, NonEmptyText


class CompactSkill(Contract):
    schema_version: Literal["compact-skill/1"] = "compact-skill/1"
    title: NonEmptyText
    principle: NonEmptyText
    when_to_apply: NonEmptyText

    @field_validator("title", "principle", "when_to_apply")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def content_limits(self) -> Self:
        validate_skill(self.title, self.principle, self.when_to_apply)
        return self

    def model_payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "principle": self.principle,
            "when_to_apply": self.when_to_apply,
        }

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.model_payload(), ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
