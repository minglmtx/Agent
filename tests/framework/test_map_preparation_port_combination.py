"""New producer with original source suffix; explicit synthetic native services."""

from pathlib import Path
from typing import Any
import pytest
import traceback
import map_task_evaluation_native
from lab_generate_skill.bootstrap.map_navigation_evaluation import (
    map_navigation_evaluator,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from map_navigation_group_cases import SOURCES
from map_navigation_source_fixtures import source_combination
from map_navigation_evaluation_fixtures import closed_review
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualified_source_native import MapQualifiedSource
from map_task_preparation_port_fixtures import bind_preparation
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("source_id", SOURCES)
def test_original_navigation_consumer_uses_production_preparation(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source_id)
    requests = []
    evaluator_factory = map_navigation_evaluator

    def diagnosed(*args: Any, **kwargs: Any) -> Any:
        evaluator = evaluator_factory(*args, **kwargs)
        original_loader = evaluator.loader

        def loader(*items: Any, **options: Any) -> Any:
            try:
                return original_loader(*items, **options)
            except BaseException:
                traceback.print_exc()
                raise

        evaluator.loader = loader
        return evaluator

    monkeypatch.setattr(
        map_task_evaluation_native, "map_navigation_evaluator", diagnosed
    )

    def prepared(
        source: MapQualifiedSource, facts: dict[str, Any]
    ) -> PreparedPublication:
        p = bind_preparation(c, source.site, source, monkeypatch)
        p.acquire()
        result_refs = p.prepare()
        state, n = p.preparation.state, source.native
        assert state.result is not None and state.snapshot_result is not None
        assert state.prepare_request is not None and state.prepare_result is not None
        assert (
            state.environment is not None
            and state.environment_selection_ref is not None
        )
        # Only adopt retained native facts for the existing engineering consumer.
        # No after_snapshot/environment/native prepare re-execution or permission.
        n.request, n.result, n.environment = (
            state.prepare_request,
            state.prepare_result,
            state.environment,
        )
        source.environment = state.environment
        source.plan, source.plan_ref = p.reset, p.reset_ref
        source.browser_token = p.reset.attempt_allocations[0]
        selection = EnvironmentSelection.model_validate_json(
            c.resource.evidence.read(state.environment_selection_ref)
        )
        source.saved.update(
            environment_selection=selection,
            environment_selection_ref=state.environment_selection_ref,
            environment_ref=state.environment_ref,
            snapshot=source.parse_snapshot(state.snapshot_result),
            snapshot_ref=state.snapshot_ref,
        )
        publication = state.result.publication
        facts.update(
            snapshot=dict(
                request=state.result.snapshot_request_ref.model_dump(mode="json"),
                result=state.result.snapshot_result_ref.model_dump(mode="json"),
                snapshot_ref=state.result.snapshot_ref.model_dump(mode="json"),
            ),
            reset_plan_ref=p.reset_ref.model_dump(mode="json"),
            preparation_records=dict(publication=publication.model_dump(mode="json")),
            task_preparation_result_ref=result_refs[0].model_dump(mode="json"),
        )
        requests.extend(p.requests)
        return publication

    try:
        facts = source_combination(c, monkeypatch, preparation=prepared)
        assert facts["judgment"]["evaluation"]["status"] == "success"
        assert facts["qualified_source"]["reset_status"] == "safe"
        assert [request.action for request in requests] == ["snapshot", "prepare"]
        closed_review(c, facts)
    finally:
        c.close_sockets()
