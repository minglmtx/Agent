"""Shared actual Actor execution/error retention; Map supplies original collectors."""

from typing import Any
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from browser_resource_fixtures import ResourceCase
from qualified_source_native import QualifiedSource
from source_actor_callbacks import SourceActorCallbacks
from map_qualified_source_native import MapQualifiedSource
from map_terminal_native import collect
from map_task_evaluation_native import judge


class MapActorCallbacks(SourceActorCallbacks):
    def collect(
        self,
        source: QualifiedSource,
        browser: ResourceCase,
        session: EvidenceBrowserSession,
    ) -> None:
        if not isinstance(source, MapQualifiedSource):
            raise TypeError("Exact selected Map source required")
        collect(source, browser, session, actor=self.facts)

    def evaluate(self, source: QualifiedSource, site_facts: dict[str, Any]) -> None:
        try:
            if not isinstance(source, MapQualifiedSource):
                raise TypeError("Exact selected Map source required")
            self.facts["judgment"] = judge(source, self.facts)
        except BaseException as error:
            self.retain("evaluation", error)
        site_facts["actor"] = self.facts
