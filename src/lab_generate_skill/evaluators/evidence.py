"""Bounded canonical evidence reads through the caller's original control."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


class EvaluationEvidence:
    def __init__(self, reader: EvidenceReader, control: OperationControl) -> None:
        self.reader, self.control = reader, control

    def read(
        self,
        ref: EvidenceRef,
        schema: str,
        model: type[T],
        *,
        public: bool = False,
        limit: int = 2 * 1024 * 1024,
    ) -> T:
        if (ref.content_schema, ref.media_type, ref.visibility) != (
            schema,
            "application/json",
            "public" if public else "private",
        ) or not 0 < ref.size_bytes <= limit:
            raise EvidenceIntegrityError(
                "Evaluation reference changed schema, visibility or bound"
            )
        self.control.checkpoint()
        raw = self.reader.read(ref, self.control)
        if (
            type(raw) is not bytes
            or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256
        ):
            raise EvidenceIntegrityError(
                "Evaluation evidence differs from its reference"
            )
        value = model.model_validate_json(raw)
        if value.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Evaluation evidence is not canonical")
        self.control.checkpoint()
        return value
