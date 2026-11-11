"""Correctable model-input facts; never permission, execution or business truth."""

from typing import Any, Literal, Self, Annotated
from pydantic import Field, model_validator
from .validation import Contract, Sha256

RejectionCode = Literal[
    "INVALID_JSON",
    "INVALID_RESPONSE_SHAPE",
    "WRONG_TOOL_BRANCH",
    "UNKNOWN_TOOL",
    "INVALID_ARGUMENTS",
    "RANGE_COUNT_EXCEEDED",
    "OUTPUT_BUDGET_EXCEEDED",
    "STALE_SNAPSHOT",
    "UNKNOWN_REGION",
    "RANGE_OUT_OF_BOUNDS",
    "INVALID_CONTINUATION",
    "READ_QUOTA_EXHAUSTED",
    "REPEATED_INVALID_PROPOSAL",
    "INVALID_PROPOSAL_LIMIT",
]


class ActorInvalidProposalProgress(Contract):
    consecutive_invalid: int = Field(default=0, ge=0, le=10000)
    repeated_invalid: int = Field(default=0, ge=0, le=10000)
    last_fingerprint: Sha256 | None = None
    fingerprints: tuple[tuple[Sha256, Annotated[int, Field(ge=1, le=10000)]], ...] = (
        Field(default=(), max_length=64)
    )

    @model_validator(mode="after")
    def original_streak(self) -> Self:
        if self.repeated_invalid > self.consecutive_invalid or (
            (self.repeated_invalid == 0) != (self.last_fingerprint is None)
        ):
            raise ValueError(
                "Rejected proposal streak requires its actual last fingerprint"
            )
        counts = dict(self.fingerprints)
        if (
            len(counts) != len(self.fingerprints)
            or sum(counts.values()) > self.consecutive_invalid
            or (
                self.last_fingerprint is not None
                and counts.get(self.last_fingerprint) != self.repeated_invalid
            )
        ):
            raise ValueError(
                "Rejected fingerprints must match the original current-snapshot streak"
            )
        return self


class ActorProposalFeedback(Contract):
    status: Literal["proposal_rejected"] = "proposal_rejected"
    executed: Literal[False] = False
    tool: str | None = Field(default=None, max_length=128)
    code: RejectionCode
    message: str = Field(max_length=2048)
    field: str | None = Field(default=None, max_length=256)
    actual: Any = None
    allowed: Any = None
    next_action: str = Field(max_length=2048)
    can_correct: bool = True
    consecutive_invalid: int = Field(default=0, ge=0, le=10000)
    repeated_invalid: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def bounded_feedback(self) -> Self:
        if len(self.model_dump_json().encode()) > 8192:
            raise ValueError("Actor correction feedback exceeds byte boundary")
        return self


class ActorProposalError(ValueError):
    """Only an explicitly confirmed proposal error may become a correction."""

    def __init__(self, feedback: ActorProposalFeedback) -> None:
        self.feedback = ActorProposalFeedback.model_validate(feedback)
        super().__init__(self.feedback.model_dump_json())
