"""Pure navigation outcome; no browser, backend query, source or admission I/O."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class NavigationOutcome:
    status: Literal["success", "failure", "unknown"]
    reward: float | None
    checks: tuple[tuple[str, bool], ...]
    reason: str | None
    version: Literal["site-navigation-v3"] | None = "site-navigation-v3"
    selected_records_unchanged: bool | None = None
    state_change_requires_review: bool | None = None

    def original_result(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "reward": self.reward,
            "checks": dict(self.checks),
            "reason": self.reason,
        }
        if self.version is not None:
            result["version"] = self.version
        if self.selected_records_unchanged is not None:
            result["selected_records_unchanged"] = self.selected_records_unchanged
        if self.state_change_requires_review is not None:
            result["state_change_requires_review"] = self.state_change_requires_review
        return result
