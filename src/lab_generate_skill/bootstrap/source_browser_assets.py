"""Installed browser assets/policy, with no task, source or execution permission."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from lab_generate_skill.domain.evidence import EvidenceRequirements


@dataclass(frozen=True)
class SourceBrowserAssets:
    """Explicit installed assets/policy, containing no task or measured state."""

    chromium_executable: str
    playwright_browsers_path: str
    library_directories: tuple[str, ...]
    seed: int
    action_timeout_ms: int
    max_events: int
    requirements: EvidenceRequirements

    def __post_init__(self) -> None:
        for path in (
            self.chromium_executable,
            self.playwright_browsers_path,
            *self.library_directories,
        ):
            if (
                type(path) is not str
                or not PurePosixPath(path).is_absolute()
                or str(PurePosixPath(path)) != path
                or ".." in PurePosixPath(path).parts
                or any(c in path for c in ("\0", ":", "\\"))
            ):
                raise ValueError("Original canonical installed browser assets required")
        if not PurePosixPath(self.chromium_executable).is_relative_to(
            self.playwright_browsers_path
        ):
            raise ValueError(
                "Source Chromium must belong to its declared browser cache"
            )
        if (
            type(self.library_directories) is not tuple
            or len(self.library_directories) > 16
            or len(set(self.library_directories)) != len(self.library_directories)
        ):
            raise ValueError("Explicit distinct browser library directories required")
        if (
            type(self.seed) is not int
            or not 0 <= self.seed <= 2**32 - 1
            or type(self.action_timeout_ms) is not int
            or not 500 <= self.action_timeout_ms <= 10000
            or type(self.max_events) is not int
            or not 4 <= self.max_events <= 4096
        ):
            raise ValueError("Source browser policy exceeds original bounds")
        if not isinstance(self.requirements, EvidenceRequirements):
            raise TypeError("Explicit typed browser evidence requirements required")
        requirements = EvidenceRequirements.model_validate(self.requirements)
        if requirements.facts or "download" in requirements.events:
            raise ValueError(
                "Source observation requires supported browser events only"
            )
