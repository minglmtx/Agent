"""Exact original pure transforms and selected full contract boundaries."""

import ast
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.map_frontend import (
    MapFrontendPlan,
    MapFrontendPrepared,
    MapFrontendChange,
    PATCH_FILES,
)
from lab_generate_skill.sites.map.frontend_sources import preparation, PRELOAD
from map_frontend_fixtures import originals
from map_services_fixtures import selected
from map_database_original_oracle import ROOT, CAPSULE
from site_instance_fixtures import node_path


def test_original_route_shortlink_preload_parity_and_unchanged_native_cap(
    node_path: Path,
) -> None:
    source = originals()
    spec = selected(node_path)
    plan = preparation(spec, source)
    raw = CAPSULE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    )
    pins = json.loads(raw)["members"]
    namespace: dict[str, Any] = {"hashlib": hashlib}
    for module, names in (
        ("map_query_site", {"remap_routing_ports", "preserve_shortlink_port"}),
        ("map_export_preload", {"preload_controller"}),
    ):
        relative = "src/lab_generate_skill/" + module + ".py"
        body = (ROOT / relative).read_bytes()
        assert hashlib.sha256(body).hexdigest() == pins[relative]["sha256"]
        tree = ast.parse(body)
        if module == "map_export_preload":
            for n in tree.body:
                if (
                    isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id in ("NATIVE_SHA256", "INSERT")
                ):
                    namespace[n.targets[0].id] = ast.literal_eval(n.value)
        funcs = [
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
        ]
        assert {n.name for n in funcs} == names
        exec(
            compile(
                ast.Module(body=list[ast.stmt](funcs), type_ignores=[]),
                relative,
                "exec",
            ),
            namespace,
        )
    changed = {c.original.path: c.content for c in plan.changes}
    engine = "app/assets/javascripts/index/directions/fossgis_osrm.js"
    leaflet = "app/assets/javascripts/leaflet.map.js"
    controller = "app/controllers/api/map_controller.rb"
    assert changed[engine].decode() == namespace["remap_routing_ports"](
        source[engine].decode(),
        {p: getattr(spec.ports, p) for p in ("car", "bike", "foot")},
    )
    assert changed[leaflet].decode() == namespace["preserve_shortlink_port"](
        source[leaflet].decode()
    )
    assert changed[controller].decode() == namespace["preload_controller"](
        source[controller].decode()
    )
    assert PRELOAD == namespace["INSERT"]
    assert (
        changed[controller].decode().replace(PRELOAD, "") == source[controller].decode()
    )
    assert "config/settings.yml" not in changed
    assert b"max_number_of_nodes: 50000" in source["config/settings.yml"]
    assert {c.original.path for c in plan.changes} == PATCH_FILES


@pytest.mark.parametrize(
    "change", ["missing", "extra", "drift", "none", "empty", "text"]
)
def test_wrong_original_full_source_set_refused(node_path: Path, change: str) -> None:
    spec = selected(node_path)
    values: Any = originals()
    key = "app/controllers/api/map_controller.rb"
    if change == "missing":
        values.pop(key)
    elif change == "extra":
        values["extra.js"] = b"x"
    elif change == "drift":
        values[key] += b"\n"
    elif change == "none":
        values = None
    elif change == "empty":
        values[key] = b""
    else:
        values[key] = values[key].decode()
    with pytest.raises(ValueError):
        preparation(spec, values)


@pytest.mark.parametrize(
    "change", ["empty", "wrong-type", "unchanged", "binary", "nul", "large"]
)
def test_invalid_patch_content(node_path: Path, change: str) -> None:
    original = originals()
    plan = preparation(selected(node_path), original)
    first = plan.changes[0]
    content: Any = {
        "empty": b"",
        "wrong-type": "text",
        "unchanged": original[first.original.path],
        "binary": b"\xff",
        "nul": b"x\0",
        "large": b"x" * (1024 * 1024 + 1),
    }[change]
    with pytest.raises(ValueError):
        MapFrontendChange(original=first.original, content=content)


def test_plan_and_receipt_reject_missing_duplicate_or_cross_spec(
    node_path: Path,
) -> None:
    plan = preparation(selected(node_path), originals())
    for update in (
        {"original": ()},
        {"changes": (plan.changes[0],) * 7},
        {"schema_version": "map-frontend-preparation/0"},
    ):
        with pytest.raises(ValueError):
            MapFrontendPlan.model_validate({**plan.model_dump(), **update})
    receipt = MapFrontendPrepared(
        preparation_sha256=plan.sha256(),
        original=plan.original,
        changed=tuple(c.after() for c in plan.changes),
    )
    receipt.check(plan)
    wrong = MapFrontendPrepared.model_validate(
        {**receipt.model_dump(), "preparation_sha256": "0" * 64}
    )
    with pytest.raises(ValueError):
        wrong.check(plan)
