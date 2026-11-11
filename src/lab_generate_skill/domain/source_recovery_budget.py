"""Explicit source recovery durations; no owner, permission or runtime grant.

These are disjoint phase allowances on the existing source recovery path.
They are not measured durations or a whole-job estimate. Callers must still
compose their real branches with execution, outer cleanup and Slurm hard end.
"""

from typing import Literal
from pydantic import Field
from .validation import Contract

RecoveryStage = Literal[
    "preparation_metadata_seconds",
    "browser_close_seconds",
    "restore_seconds",
    "resume_seconds",
    "reset_facts_seconds",
    "site_close_seconds",
]


class SourceRecoveryBudgets(Contract):
    schema_version: Literal["source-recovery-budgets/1"] = "source-recovery-budgets/1"
    preparation_metadata_seconds: int = Field(ge=1, le=1800)
    browser_close_seconds: int = Field(ge=1, le=3600)
    restore_seconds: int = Field(ge=1, le=1200)
    resume_seconds: int = Field(ge=1, le=600)
    reset_facts_seconds: int = Field(ge=1, le=1800)
    site_close_seconds: int = Field(ge=1, le=3600)

    def seconds(self, stage: RecoveryStage) -> int:
        values: dict[RecoveryStage, int] = {
            "preparation_metadata_seconds": self.preparation_metadata_seconds,
            "browser_close_seconds": self.browser_close_seconds,
            "restore_seconds": self.restore_seconds,
            "resume_seconds": self.resume_seconds,
            "reset_facts_seconds": self.reset_facts_seconds,
            "site_close_seconds": self.site_close_seconds,
        }
        return values[stage]

    @property
    def complete_recovery_path_seconds(self) -> int:
        # Browser's registered cleanup and outer close use the same allowance;
        # they are nested, not two phases to add. Unknown branches skip replay.
        return (
            self.browser_close_seconds
            + self.restore_seconds
            + self.resume_seconds
            + self.reset_facts_seconds
            + self.site_close_seconds
        )


def recovery_seconds(
    budgets: SourceRecoveryBudgets | None, stage: RecoveryStage, legacy: int
) -> int:
    """None preserves exact old caller behavior; new recipes supply all fields."""
    if budgets is None:
        return legacy
    return SourceRecoveryBudgets.model_validate(budgets).seconds(stage)
