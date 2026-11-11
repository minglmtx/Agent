"""Selected publication identities and strict consumed-leaf contracts."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.read_inputs import PublishedMapInputs
from lab_generate_skill.adapters.map_runtime.inventory import parse_inventory
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.domain.map_runtime_inputs import (
    IMAGE_PINS,
    MapRuntimeInputs,
    MapRuntimeTree,
)
from lab_generate_skill.domain.map_services import MapPorts, MapServiceSpec
from map_runtime_fixtures import runtime_case, save
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_five_image_pins_match_accepted_original_migration_receipt() -> None:
    path = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/admin/website-workspace-images-v2/switch-result.json"
    )
    receipt = json.loads(path.read_text())
    assert receipt["passed"] is True and str(receipt["job_id"]) == "4694114"
    images = {
        row["asset"].split("/")[1]: (row["sha256"], row["bytes"])
        for row in receipt["images"]
        if row["asset"].startswith("map/")
    }
    assert IMAGE_PINS == images


def test_five_exact_images_trees_and_six_ports(node_path: Path) -> None:
    plan = runtime_case(node_path)
    inventories = PublishedMapInputs().read(plan, guard())
    assert len(inventories) == 5 and {i.role for i in inventories} == {
        t.role for t in plan.trees
    }
    assert len(inventories[2].files) == 80
    assert not any(x.file.path.endswith(".osrm") for x in inventories[2].files)
    assert any(x.file.path == "Gemfile.lock" for x in inventories[-1].files)
    assert PublishedMapInputs().read(plan, guard()) == inventories  # read-only repeat
    ports = MapPorts(web=1024, search=65535, car=3333, bike=3334, foot=3335, tiles=3336)
    spec = MapServiceSpec(inputs=plan, ports=ports)
    assert spec.endpoint == "http://127.0.0.1:1024/"
    assert spec.state_root("frontend") == plan.files.state_root + "/frontend"
    assert plan.node_image("db").endswith("/image/db.sif")
    assert plan.node_tree("routing").endswith("/input/routing")
    assert not Path(plan.files.node_root).exists()


@pytest.mark.parametrize(
    "update",
    [
        {"images": ()},
        {"trees": None},
        {"trees": []},
        {"selected_source": "other"},
        {"schema_version": "map-native-runtime-inputs/0"},
        {"publication_job_id": True},
        {"publication_job_id": "0"},
        {"publication_path": "/outside/publication.json"},
        {"unknown": 1},
    ],
)
def test_invalid_input_contract_before_effect(
    node_path: Path, update: dict[str, Any]
) -> None:
    plan = runtime_case(node_path)
    with pytest.raises(ValueError):
        MapRuntimeInputs.model_validate({**plan.model_dump(), **update})
    assert not Path(plan.files.node_root).exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("web", 1),
        ("web", 65536),
        ("web", True),
        ("search", 1024),
        ("car", None),
        ("tiles", "3336"),
    ],
)
def test_invalid_or_duplicate_ports(field: str, value: Any) -> None:
    ports = dict(web=1024, search=65535, car=3333, bike=3334, foot=3335, tiles=3336)
    with pytest.raises(ValueError):
        MapPorts.model_validate({**ports, field: value})


@pytest.mark.parametrize(
    "change",
    [
        "job",
        "failed",
        "effects",
        "bool-count",
        "missing-tree",
        "repeated-tree",
        "inventory-pin",
        "destination",
        "total",
    ],
)
def test_published_receipt_mismatch_refused(node_path: Path, change: str) -> None:
    plan = runtime_case(node_path)
    path = Path(plan.publication_path)
    receipt = json.loads(path.read_text())
    if change == "job":
        receipt["job_id"] = "54321"
    elif change == "failed":
        receipt["passed"] = False
    elif change == "effects":
        receipt["services_started"] = 1
    elif change == "bool-count":
        receipt["model_calls"] = False
    elif change == "missing-tree":
        receipt["trees"].pop()
    elif change == "repeated-tree":
        receipt["trees"][1] = receipt["trees"][0]
    elif change == "inventory-pin":
        receipt["trees"][0]["inventory"]["sha256"] = "0" * 64
    elif change == "destination":
        receipt["trees"][0]["destination"] += "-wrong"
    else:
        receipt["trees"][0]["bytes"] += 1
    revised = MapRuntimeInputs.model_validate(
        {**plan.model_dump(), "publication": save(path, receipt)}
    )
    with pytest.raises(ValueError):
        PublishedMapInputs().read(revised, guard())
    assert not Path(plan.files.node_root).exists()


@pytest.mark.parametrize(
    "change",
    [
        "missing-leaf",
        "alias",
        "extra-field",
        "bad-relative",
        "bool-size",
        "bad-mode",
        "duplicate",
        "parent",
        "excluded",
        "bytes",
        "empty",
    ],
)
def test_complete_inventory_rejects_invalid_shapes(
    node_path: Path, change: str
) -> None:
    plan = runtime_case(node_path)
    declaration = plan.trees[0]
    raw = json.loads(Path(declaration.inventory_path).read_text())
    if change == "missing-leaf":
        removed = raw["files"].pop(0)
        raw["bytes"] -= removed["bytes"]
    elif change == "alias":
        raw["files"][0]["resolved_source"] = "/other/baseline.json"
    elif change == "extra-field":
        raw["default"] = True
    elif change == "bad-relative":
        raw["files"][0]["relative"] = "../escape"
    elif change == "bool-size":
        raw["files"][0]["bytes"] = True
    elif change == "bad-mode":
        raw["files"][0]["state"][5] = 0o4600
    elif change == "duplicate":
        raw["files"].append(raw["files"][0])
    elif change == "parent":
        raw["directories"].remove("postgres")
    elif change == "excluded":
        raw["excluded"] = ["postgres"]
    elif change == "bytes":
        raw["bytes"] += 1
    else:
        raw["files"] = []
    with pytest.raises(ValueError):
        parse_inventory(raw, declaration)


@pytest.mark.parametrize(
    "body",
    [
        b"{}{}",
        b"[]",
        b"null",
        b'{"x":1,"x":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":{"y":1,"y":2}}',
        b"\xff",
    ],
)
def test_malformed_metadata_is_not_guessed(body: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        object_json(body)


def test_image_pin_role_duplicates_and_tree_overlap_refused(node_path: Path) -> None:
    plan = runtime_case(node_path)
    values = plan.model_dump()
    values["images"][0]["file"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        MapRuntimeInputs.model_validate(values)
    with pytest.raises(ValueError):
        MapRuntimeInputs.model_validate(
            {**plan.model_dump(), "images": (plan.images[0],) * 5}
        )
    wrong = MapRuntimeTree.model_validate(
        {
            **plan.trees[0].model_dump(),
            "source_root": str(Path(plan.publication_path).parent),
        }
    )
    with pytest.raises(ValueError):
        MapRuntimeInputs.model_validate(
            {**plan.model_dump(), "trees": (wrong, *plan.trees[1:])}
        )
