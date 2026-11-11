"""Explicit engineering task composition on an existing fresh native source."""

from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, TYPE_CHECKING
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from evidence_control_fixtures import EvidenceFixtureStore
from browser_resource_fixtures import ResourceCase
from reddit_source_selection import RedditSourceSelection
from gitlab_source_selection import GitlabSourceSelection
from map_navigation_source_selection import MapNavigationSourceSelection

if TYPE_CHECKING:
    from qualified_source_native import QualifiedSource


@dataclass(frozen=True)
class SourceTaskHooks:
    owner: ResourceOwner
    evidence: EvidenceFixtureStore
    allowed_actions: tuple[str, ...]
    execute: Callable[
        [QualifiedSource, ResourceCase, EvidenceBrowserSession, dict[str, Any]], None
    ]
    evaluate: Callable[[QualifiedSource, dict[str, Any]], None]
    private_site_plan: SitePrivateEvidencePlan | None = None
    reddit_selection: RedditSourceSelection | None = None
    gitlab_selection: GitlabSourceSelection | None = None
    map_selection: MapNavigationSourceSelection | None = None

    def __post_init__(self) -> None:
        if self.map_selection is not None:
            if not isinstance(self.map_selection, MapNavigationSourceSelection):
                raise TypeError(
                    "Explicit validated selected8 Map navigation source required"
                )
            if (
                self.reddit_selection is not None
                or self.gitlab_selection is not None
                or self.private_site_plan is not None
            ):
                raise ValueError(
                    "One original selected Map source without foreign private profile required"
                )
        if self.reddit_selection is not None and not isinstance(
            self.reddit_selection, RedditSourceSelection
        ):
            raise TypeError("Explicit validated Reddit selection required")

        if self.gitlab_selection is not None:
            if not isinstance(self.gitlab_selection, GitlabSourceSelection):
                raise TypeError("Explicit validated GitLab selection required")
            if self.reddit_selection is not None:
                raise ValueError("One original selected site required")
            if (
                self.private_site_plan is not None
                and self.private_site_plan.profile != self.gitlab_selection.profile
            ):
                raise ValueError("GitLab selection changed declared private profile")

    def session(
        self, source: QualifiedSource
    ) -> Callable[[ResourceCase, EvidenceBrowserSession, dict[str, Any]], None]:
        return lambda browser, session, result: self.execute(
            source, browser, session, result
        )
