"""Retain task errors until original browser closure and site recovery complete."""

from pathlib import Path
from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    actor_projection_configuration,
)
from typing import Any
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from actor_resource_fixtures import ResourceCase as ActorCase
from browser_resource_fixtures import ResourceCase as BrowserCase
from qualified_source_native import QualifiedSource
from source_actor_execution import execute_source_actor
from source_task_evaluation import final_page, judge_source_task


class SourceActorCallbacks:
    def __init__(
        self,
        actor: ActorCase,
        scope: ActorExecutionScope,
        params: LocalActorParameters,
        root: Path,
        *,
        context_policy: ContextProjectionPolicy,
        max_interactions: int = 16,
        projection: ActorProjectionConfiguration | None = None,
    ) -> None:
        if type(max_interactions) is not int or not 1 <= max_interactions <= 20:
            raise ValueError(
                "Explicit engineering interaction limit must be integer1..20"
            )
        self.projection = (
            None if projection is None else actor_projection_configuration(projection)
        )
        self.max_interactions = max_interactions
        self.context_policy = ContextProjectionPolicy.model_validate(context_policy)
        if self.context_policy.role != "actor":
            raise ValueError("Actor source requires original Actor context policy")
        self.actor, self.scope, self.params, self.root = actor, scope, params, root
        self.facts: dict[str, Any] = {}
        self.errors: list[BaseException] = []

    def retain(self, phase: str, error: BaseException) -> None:
        self.errors.append(error)
        self.facts.setdefault("errors", []).append(
            dict(phase=phase, error=describe_error(error).model_dump(mode="json"))
        )

    def execute(
        self,
        source: QualifiedSource,
        browser: BrowserCase,
        session: EvidenceBrowserSession,
        observed: dict[str, Any],
    ) -> None:
        try:
            result, failure = execute_source_actor(
                source,
                browser,
                session,
                self.actor,
                self.scope,
                self.params,
                self.root,
                max_interactions=self.max_interactions,
                projection=self.projection,
                context_policy=self.context_policy,
            )
            self.facts.update(result)
            if failure is not None:
                self.retain("actor", failure)
        except BaseException as error:
            self.retain("actor", error)
        # No recovery/retry of an unknown transport. The resource manager still
        # owns original closure; caller only restores after confirmed closure.
        if session.engine.state in ("ready", "terminal"):
            try:
                self.collect(source, browser, session)
            except BaseException as error:
                self.retain("page_capture", error)
        else:
            self.facts["page_capture_unavailable"] = session.engine.state
        observed["actor"] = self.facts

    def collect(
        self,
        source: QualifiedSource,
        browser: BrowserCase,
        session: EvidenceBrowserSession,
    ) -> None:
        self.facts["page_capture"] = final_page(source, browser, session).model_dump(
            mode="json"
        )

    def evaluate(self, source: QualifiedSource, site_facts: dict[str, Any]) -> None:
        try:
            self.facts["judgment"] = judge_source_task(source, site_facts, self.facts)
        except BaseException as error:
            self.retain("evaluation", error)
        site_facts["actor"] = self.facts
