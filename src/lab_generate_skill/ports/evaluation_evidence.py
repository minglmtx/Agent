"""Typed canonical fact reads and existing trace-answer verification dependencies.

The composition root supplies the implementations. These ports do not grant
new reads, dispatch or task authority, and supply no synchronous fallback.
"""

from typing import Protocol, TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.task import PublicTask

T = TypeVar("T", bound=Contract)


class EvaluationEvidenceReader(Protocol):
    def read(
        self,
        ref: EvidenceRef,
        schema: str,
        model: type[T],
        *,
        public: bool = False,
        limit: int = 2 * 1024 * 1024,
    ) -> T: ...


class TraceAnswerReader(Protocol):
    def __call__(
        self,
        trace: InteractionTrace,
        task: PublicTask,
        evidence: EvaluationEvidenceReader,
    ) -> str | None: ...
