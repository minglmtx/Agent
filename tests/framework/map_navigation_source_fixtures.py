"""Actual source adapters/Actor callback with one shared explicit synthetic backend."""

from pathlib import Path
from collections.abc import Callable
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.evidence import EvidenceRef
from typing import Any
import os
import pytest
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.errors import OwnershipConflict
from map_navigation_fixtures import navigation_case
from map_navigation_source_selection import MapNavigationSourceSelection
from map_navigation_group_cases import MEMBERS
from map_navigation_browser_resource_fixtures import (
    navigation_browser_resource,
    NavigationBrowserDouble,
)
from map_navigation_browser_fixtures import Page
from map_navigation_evaluation_fixtures import (
    bind_original_contract,
    retain_closed_proof,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_source_inputs import MapSourceInputs
from map_qualification_fixtures import configure_qualification
from map_qualified_source_native import MapQualifiedSource
from map_actor_trace_fixtures import execute_browser_actor
from map_actor_callbacks import MapActorCallbacks
from map_source_lifecycle_native import run, run_prepared
from map_source_native_boundary_fixtures import source_native_boundary
from map_task_operations_native import execute as execute_operation
from actor_context_projection_fixtures import actor_projection_case
from source_task_hooks import SourceTaskHooks
from test_site_resource import enter
from browser_resource_fixtures import ResourceCase
import prepared_browser_native
import source_actor_callbacks


def selection(source: str) -> MapNavigationSourceSelection:
    original = navigation_case(source)
    return MapNavigationSourceSelection(original.raw, original.binding, original.public)


def source_combination(
    c: RegisteredMapCase,
    patch: pytest.MonkeyPatch,
    *,
    negative: bool = False,
    missing_trace: bool = False,
    preparation: (
        Callable[[MapQualifiedSource, dict[str, Any]], PreparedPublication] | None
    ) = None,
) -> dict[str, Any]:
    bind_original_contract(c)
    spec_ref, _ = configure_qualification(c, patch)
    chosen = selection(c.scope.task.source_task_id)
    inputs = MapSourceInputs(c.configuration, c.private, None, spec_ref, None, chosen)
    retain_closed_proof(patch)
    backends: list[NavigationBrowserDouble] = []
    source_id = c.scope.task.source_task_id
    row = next(r for r in MEMBERS if r[0] == source_id)

    def effect(page: Page, payload: str) -> None:
        assert payload == "click('a')"
        page.url = (
            page.url.split("/", 3)[0]
            + "//"
            + page.url.split("/", 3)[2]
            + ("/about" if negative else row[1])
        )
        page.headings = ["Wrong named document" if negative else row[2]]

    def browser(
        root: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
    ) -> ResourceCase:
        assert kwargs["real_step"] is True
        backend = navigation_browser_resource(
            root,
            monkeypatch,
            configuration=kwargs["config"],
            store=c.resource.evidence,
            declared_token=kwargs["declared_token"],
            site=c.resource.spec,
            public_text="RootWebArea 'Map navigation'\n  [a] link 'Requested local document'",
            step_effect=effect,
        )
        backends.append(backend)
        return backend.resource

    patch.setattr(prepared_browser_native, "resource_case", browser)
    patch.setattr(
        prepared_browser_native,
        "EngineeringTreeAuthority",
        lambda store: backends[-1].resource.authority,
    )
    with enter(c.resource) as site:
        source = MapQualifiedSource(
            c.resource, site, inputs, allowed_actions=("click", "send_msg_to_user")
        )
        c.binding, c.task_recovery = (
            source.native.binding_ref,
            source.native.recovery_ref,
        )
        captured: list[str] = []
        source_native_boundary(c, source, patch, captured)

        def actor(
            s: Any,
            b: Any,
            session: Any,
            *args: Any,
            max_interactions: int,
            context_policy: Any,
            projection: Any = None,
        ) -> Any:
            assert s is source and b is backends[0].resource
            assert max_interactions == 16 and isinstance(projection, FullAxProjection)
            if missing_trace:
                return {}, None
            trace_ref, snapshot_ref, trace, _ = execute_browser_actor(c, b, session)
            return (
                dict(
                    trace_ref=trace_ref.model_dump(mode="json"),
                    trace_snapshot_ref=snapshot_ref.model_dump(mode="json"),
                    verified_model_returns=1,
                    generations=trace.generations,
                    interactions=trace.interactions,
                ),
                None,
            )

        patch.setattr(source_actor_callbacks, "execute_source_actor", actor)
        unit: Any = None
        callbacks = MapActorCallbacks(
            unit,
            unit,
            unit,
            c.workspace / "unused-model-root",
            context_policy=actor_projection_case().policy,
            projection=FullAxProjection(),
        )
        hooks = SourceTaskHooks(
            c.scope.owner,
            c.resource.evidence,
            ("click", "send_msg_to_user"),
            callbacks.execute,
            callbacks.evaluate,
            map_selection=chosen,
        )
        facts: dict[str, Any] = {}
        if preparation is None:
            run(source, hooks, c.workspace, patch, facts)
        else:
            publication = preparation(source, facts)
            run_prepared(
                source,
                hooks,
                c.workspace,
                patch,
                facts,
                publication,
                EvidenceRef.model_validate(facts["snapshot"]["snapshot_ref"]),
            )
        if callbacks.errors and not missing_trace:
            import traceback

            for error in callbacks.errors:
                traceback.print_exception(error)
        assert not callbacks.errors or missing_trace, callbacks.facts
        value = callbacks.facts["judgment"]["evaluation"]
        assert value["status"] == (
            "unknown" if missing_trace else "failure" if negative else "success"
        )
        assert value["reward"] == (None if missing_trace else 0 if negative else 1)
        assert captured == ["map-navigation-state"]
        assert facts["qualified_source"]["reset_status"] == "safe"
        assert facts["prepared_browser"]["complete_baseline"] is True
        assert c.worker is not None and c.worker.references is None
        before = (len(c.case.commands.calls), len(c.sql.calls))
        with pytest.raises(OwnershipConflict):
            execute_operation(source, "restore", source.saved["snapshot_ref"])
        assert (len(c.case.commands.calls), len(c.sql.calls)) == before
        facts.update(
            judgment=callbacks.facts["judgment"],
            configuration=c.resource.spec.model_dump(mode="json"),
            started=source.site.site.model_dump(mode="json"),
            engineering_only=True,
            synthetic_kernel=True,
            original_process=os.getpid(),
            evidence_root=str(c.workspace / "evidence"),
            expected_status=value["status"],
        )
        assert len(backends) == 1 and backends[0].calls.count("project") == (
            1 if missing_trace else 2
        )
    return facts
