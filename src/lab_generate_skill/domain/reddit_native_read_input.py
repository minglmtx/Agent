"""Private scoped baseline-id artifact, declared without file I/O or admission."""

from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Sha256
from .identity import TaskIdentity

NativeId = Annotated[int, Field(ge=1, le=2**63 - 1)]

MAX_BASELINE_BYTES = 64 * 1024**2


class BaselineIdsPayload(Contract):
    schema_version: Literal["reddit-native-baseline-ids/1"] = (
        "reddit-native-baseline-ids/1"
    )
    task: TaskIdentity
    request_sha256: Sha256
    count: int = Field(ge=0, le=2**63 - 1)
    ranges: tuple[tuple[NativeId, NativeId], ...] = Field(max_length=1000000)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) != ("reddit", "native_image_submission", 1, "train"):
            raise ValueError("Original selected Reddit train task required")
        end = 0
        covered = 0
        for lo, hi in self.ranges:
            if not end < lo <= hi:
                raise ValueError("Complete disjoint native id ranges required")
            covered += hi - lo + 1
            end = hi
        if covered != self.count:
            raise ValueError("Baseline id ranges do not cover original count")
        return self


class BaselineIdsRef(Contract):
    schema_version: Literal["reddit-native-baseline-ids-ref/1"] = (
        "reddit-native-baseline-ids-ref/1"
    )
    task: TaskIdentity
    request_sha256: Sha256
    filename: str = Field(pattern=r"^[0-9a-f]{64}\.json$")
    sha256: Sha256
    size_bytes: int = Field(gt=0, le=MAX_BASELINE_BYTES)

    @model_validator(mode="after")
    def exact_filename(self) -> Self:
        if self.filename != self.request_sha256 + ".json":
            raise ValueError(
                "Baseline input filename must retain original snapshot request"
            )
        return self


class BaselineIdsUnconfirmed(RuntimeError):
    def __init__(self, reference: BaselineIdsRef) -> None:
        self.reference = reference
        super().__init__(
            "Native baseline file is known; reconcile original result without rewriting"
        )
