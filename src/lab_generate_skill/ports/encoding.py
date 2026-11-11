"""A fixed model/config scoring instance; lifecycle belongs to the worker owner."""

from typing import Protocol
from lab_generate_skill.domain.encoding import (
    EncodedScores,
    EncoderFiles,
    EncoderConfig,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class ScoreEncoder(Protocol):
    @property
    def files(self) -> EncoderFiles: ...
    @property
    def config(self) -> EncoderConfig: ...
    def score(
        self, documents: tuple[str, ...], query: str, control: OperationControl
    ) -> EncodedScores: ...
    def close(self, control: OperationControl) -> None: ...
