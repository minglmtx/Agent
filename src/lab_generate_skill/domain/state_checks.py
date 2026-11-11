"""Declared state coverage and attributable results, independent of websites.

Missing/unknown checks stay unknown. A failed declared check never disappears
because another component restored successfully. Content authenticity is checked
by the eventual producer/consumer adapter, not by constructing these objects.
"""

from typing import Literal, Self
from pydantic import Field, field_validator, model_validator
from .evaluation import CheckResult
from .identity import TaskIdentity
from .validation import Contract, Identifier


class StateChecks(Contract):
    schema_version: Literal["state-checks/1"] = "state-checks/1"
    required: tuple[Identifier, ...] = Field(min_length=1)
    checks: tuple[CheckResult, ...] = ()

    @model_validator(mode="after")
    def coverage(self) -> Self:
        names = tuple(c.name for c in self.checks)
        if len(set(self.required)) != len(self.required) or len(set(names)) != len(
            names
        ):
            raise ValueError("Required and observed state check names must be unique")
        if names != tuple(name for name in self.required if name in names):
            raise ValueError("Checks must be an ordered subset of declared coverage")
        for check in self.checks:
            if check.status != "unknown" and not check.evidence:
                raise ValueError("Pass/fail state facts require evidence")
            if any(r.visibility != "private" for r in check.evidence):
                raise ValueError("State verification facts remain private")
        return self

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            name for name in self.required if name not in {c.name for c in self.checks}
        )

    @property
    def status(self) -> Literal["pass", "fail", "unknown"]:
        if self.missing or any(c.status == "unknown" for c in self.checks):
            return "unknown"
        return "fail" if any(c.status == "fail" for c in self.checks) else "pass"


class InitialStateSpec(Contract):
    """Frozen task-specific coverage; does not contain a second observation."""

    schema_version: Literal["initial-state-spec/1"] = "initial-state-spec/1"
    spec_id: Identifier
    task: TaskIdentity
    environment_checks: tuple[Identifier, ...] = Field(min_length=1)
    preparation_checks: tuple[Identifier, ...] = Field(min_length=1)
    initial_checks: tuple[Identifier, ...] = Field(min_length=1)
    equivalence_checks: tuple[Identifier, ...] = Field(min_length=1)
    task_reset_checks: tuple[Identifier, ...] = Field(min_length=1)
    environment_reset_checks: tuple[Identifier, ...] = Field(min_length=1)
    health_checks: tuple[Identifier, ...] = Field(min_length=1)

    @field_validator(
        "environment_checks",
        "preparation_checks",
        "initial_checks",
        "equivalence_checks",
        "task_reset_checks",
        "environment_reset_checks",
        "health_checks",
    )
    @classmethod
    def distinct(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("State coverage cannot repeat names")
        return value
