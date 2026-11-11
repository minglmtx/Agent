"""Navigation wire/asset provenance and strict scopes, without native dispatch."""

import json
from pathlib import Path
from site_instance_fixtures import node_path as node_path
from typing import Any
import pytest
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_worker_inputs import MapWorkerInputs
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from map_navigation_file_fixtures import navigation_files
from map_navigation_fixtures import SOURCES


@pytest.mark.parametrize("source", SOURCES)
def test_navigation_wire_binds_exact_source_and_preserves_asset_provenance(
    node_path: Path, source: str
) -> None:
    c = navigation_files(node_path, source)
    inputs = c.inputs
    assert inputs.scope.task.source_task_id == source
    assert inputs.runtime.selected_source == "b9101b71aacd51b61f6e"
    assert (
        SiteWorkerConfiguration.model_validate_json(c.configuration.model_dump_json())
        == c.configuration
    )
    assert isinstance(
        SiteWorkerConfiguration.model_validate_json(
            c.configuration.model_dump_json()
        ).map_inputs,
        MapNavigationWorkerInputs,
    )
    # The old exact MapData input remains a distinct concrete contract.
    raw = json.loads(inputs.model_dump_json())
    raw.pop("native_contract_sha256")
    raw["schema_version"] = "map-worker-inputs/1"
    with pytest.raises(ValueError):
        MapWorkerInputs.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "field,value",
    [
        ("family", "native_route_map_data"),
        ("contract_version", 2),
        ("split", "test"),
        ("site", "reddit"),
        ("task_id", "0189de83adbd18ca5109"),
        ("source_task_id", "unselected"),
    ],
)
def test_navigation_rejects_wrong_source_scope(
    node_path: Path, field: str, value: Any
) -> None:
    c = navigation_files(node_path)
    raw = json.loads(c.inputs.model_dump_json())
    raw["scope"]["task"][field] = value
    with pytest.raises(ValueError):
        MapNavigationWorkerInputs.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "map-navigation-worker-inputs/0"),
        ("native_contract_sha256", "a" * 64),
        ("native_contract_sha256", None),
        ("native_contract_sha256", False),
        ("private_input_sha256", ""),
        ("max_files", 0),
        ("max_files", True),
        ("max_files", 10001),
        ("max_file_bytes", 2 * 1024**4 + 1),
        ("max_file_bytes", 128 * 1024**2 + 1),
        ("artifact_root", "relative"),
        ("artifact_root", ""),
        ("artifact_root", "/outside-workspace"),
        ("artifact_root", None),
        ("resource_journal_root", []),
    ],
)
def test_navigation_rejects_illegal_contract_budgets_and_roots(
    node_path: Path, field: str, value: Any
) -> None:
    c = navigation_files(node_path)
    raw = json.loads(c.inputs.model_dump_json())
    raw[field] = value
    with pytest.raises(ValueError):
        MapNavigationWorkerInputs.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "overlap", ["workspace", "evidence", "journal", "tree", "image"]
)
def test_navigation_roots_do_not_overlap_control_or_frozen_inputs(
    node_path: Path, overlap: str
) -> None:
    c = navigation_files(node_path)
    inputs = c.inputs
    roots = {
        "workspace": str(c.workspace),
        "evidence": inputs.evidence_root,
        "journal": inputs.resource_journal_root,
        "tree": inputs.runtime.trees[0].source_root,
        "image": inputs.runtime.images[0].source_path,
    }
    with pytest.raises(ValueError):
        MapNavigationWorkerInputs.model_validate(
            {**inputs.model_dump(), "artifact_root": roots[overlap]}
        )


def test_navigation_runtime_source_is_asset_pin_and_other_site_refuses_inputs(
    node_path: Path,
) -> None:
    c = navigation_files(node_path)
    raw = json.loads(c.configuration.model_dump_json())
    raw["map_inputs"]["runtime"]["selected_source"] = SOURCES[0]
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate_json(json.dumps(raw))
    raw = json.loads(c.configuration.model_dump_json())
    raw["site_id"] = "shopping"
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate_json(json.dumps(raw))
    raw = json.loads(c.configuration.model_dump_json())
    raw["map_inputs"]["ignored_extra_field"] = True
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("value", [None, {}, [], "", False, 1])
def test_navigation_requires_complete_typed_input(value: Any) -> None:
    with pytest.raises(ValueError):
        MapNavigationWorkerInputs.model_validate(value)
