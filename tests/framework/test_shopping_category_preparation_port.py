"""Category preparation on the original producer and protocol, no real source grant."""

from pathlib import Path
from typing import Any
import pytest
from shopping_category_preparation_port_fixtures import preparation_case, combined_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault", ["none", "source-denied", "cancel-after-snapshot", "prepared-write"]
)
def test_category_original_preparation_keeps_requests_and_closes_partial_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    facts = preparation_case(tmp_path, node_path, monkeypatch, originals[0], fault)
    assert facts["resource_closed"]
    if fault == "none":
        assert facts["result"].schema_version == "site-task-prepared/2"
        assert facts["preparer"].state.phase == "prepared"
    elif fault == "source-denied":
        assert not facts["requests"]
    elif fault == "cancel-after-snapshot":
        assert [r.action for r in facts["requests"]] == ["snapshot"]
    else:
        assert [r.action for r in facts["requests"]] == ["snapshot", "prepare"]
        assert facts["failure"].known_result is not None


@pytest.mark.parametrize("fault", ["none", "cancel-after-capture", "initial-write"])
def test_same_frozen_plan_real_preparation_to_initializer_and_original_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    facts = combined_case(tmp_path, node_path, monkeypatch, originals[0], fault)
    assert facts["source_frozen_before_candidate_snapshot"] and facts["closed"]
    assert facts["actual_prepared_result_ref"] == facts["preparer"].state.result_ref
    if fault == "none":
        assert facts["result"].actor.task.identity == originals[0][2].identity
