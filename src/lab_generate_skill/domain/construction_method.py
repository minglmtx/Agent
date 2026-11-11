"""Frozen construction schedule and worst-case work counts, without I/O.

All method values are explicit inputs: no plugin defaults or legacy imports.
The v1 method retains four candidates, top-six retrieval, four duplicate
resamples and at most three Teacher revisions, including the mandatory first.
Progress/selection decides which bounded calls are needed; these counts do not
authorize replaying an effective failure or an uncertain provider request.
"""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .validation import Contract


class ConstructionMethod(Contract):
    schema_version: Literal["construction-method/1"] = "construction-method/1"
    candidates: Literal[4]
    top_k: Literal[6]
    duplicate_resamples: Literal[4]
    teacher_rounds: Literal[3]
    seed: int = Field(ge=0, le=2147483628)
    generator_temperatures: tuple[float, float, float, float, float]
    first_teacher_required: Literal[True]
    selection_metric: Literal["recorded_environment_step_returns_v1"]

    @field_validator(
        "candidates", "top_k", "duplicate_resamples", "teacher_rounds", mode="before"
    )
    @classmethod
    def exact_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Method counts must be exact integers")
        return value

    @field_validator("first_teacher_required", mode="before")
    @classmethod
    def exact_bool(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("Mandatory Teacher flag must be boolean")
        return value

    @model_validator(mode="after")
    def unchanged_temperatures(self) -> Self:
        # Accept equivalent decimal spellings, while preserving supplied values
        # in the frozen plan and subsequent request parameter digests.
        for index, value in enumerate(self.generator_temperatures):
            if not abs(value - min(1.2, 0.7 + 0.1 * index)) <= 1e-12:
                raise ValueError("Generator temperature schedule differs from v1")
        return self

    def generator_sampling(self, candidate: int, resample: int) -> tuple[int, float]:
        if type(candidate) is not int or not 0 <= candidate < self.candidates:
            raise ValueError("Candidate index outside the frozen schedule")
        if type(resample) is not int or not 0 <= resample <= self.duplicate_resamples:
            raise ValueError("Resample index outside the frozen schedule")
        return (
            self.seed + candidate + resample * self.candidates,
            self.generator_temperatures[resample],
        )

    def teacher_seed(self, round_index: int) -> int:
        if type(round_index) is not int or not 1 <= round_index <= self.teacher_rounds:
            raise ValueError("Teacher round outside the frozen schedule")
        return self.seed + round_index - 1

    @property
    def max_attempts(self) -> int:
        return self.candidates + self.teacher_rounds

    @property
    def max_generator_requests(self) -> int:
        return self.candidates * (1 + self.duplicate_resamples)
