"""Ordered index, original document template and encoded-result binding checks."""

import hashlib
import json
from typing import Literal, Self

from pydantic import TypeAdapter, model_validator

from .bank import SkillRecord
from .encoding import EncodedScores, EncoderConfig, EncoderFiles
from .errors import OwnershipConflict
from .validation import Contract, Identifier, Sha256


class IndexEntry(Contract):
    skill_id: Identifier
    content_digest: Sha256


class RetrievalIndex(Contract):
    schema_version: Literal["retrieval-index/1"] = "retrieval-index/1"
    entries: tuple[IndexEntry, ...]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({e.skill_id for e in self.entries}) != len(self.entries):
            raise ValueError("Duplicate retrieval index entry")
        return self

    def check_records(self, records: tuple[SkillRecord, ...]) -> None:
        if tuple((e.skill_id, e.content_digest) for e in self.entries) != tuple(
            (r.skill_id, r.content_digest) for r in records
        ):
            raise OwnershipConflict(
                "Index must bind the entire ordered bank, not a subset or reordered list"
            )


def document_texts(records: tuple[SkillRecord, ...]) -> tuple[str, ...]:
    checked: tuple[SkillRecord, ...] = TypeAdapter(
        tuple[SkillRecord, ...]
    ).validate_python(records, strict=True)
    return tuple(
        f"Title: {r.skill.title}\nPrinciple: {r.skill.principle}\nWhen to apply: {r.skill.when_to_apply}"
        for r in checked
    )


def validate_encoded(
    value: EncodedScores,
    documents: tuple[str, ...],
    query: str,
    files: EncoderFiles,
    config: EncoderConfig,
) -> EncodedScores:
    value = EncodedScores.model_validate(value)
    files = EncoderFiles.model_validate(files)
    config = EncoderConfig.model_validate(config)
    expected = (
        files.digest,
        hashlib.sha256(config.model_dump_json().encode()).hexdigest(),
        hashlib.sha256(
            json.dumps(documents, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
        hashlib.sha256(query.encode()).hexdigest(),
        len(documents),
    )
    actual = (
        value.model_files_sha256,
        value.config_sha256,
        value.documents_sha256,
        value.query_sha256,
        len(value.scores),
    )
    if actual != expected:
        raise OwnershipConflict(
            "Encoded scores differ from frozen model/config or complete input batch"
        )
    return value
