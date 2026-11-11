"""Exact fourteen original frontend test files in a small private runtime clone."""

from contextlib import contextmanager
from collections.abc import Iterator
import hashlib
import json
from pathlib import Path
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_runtime_inputs import (
    MapRuntimeInputs,
    MapRuntimeTree,
)
from lab_generate_skill.adapters.map_runtime.frontend import NativeMapFrontendFiles
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.sites.map.frontend import MapFrontendPreparation
from lab_generate_skill.sites.map.frontend_sources import PINS
from lab_generate_skill.sites.map.service_controls import controls
from lab_generate_skill.sites.map.services import MapGeneration
from map_services_fixtures import selected, cloned, Commands, Group
from map_served_fixtures import originals as served_originals
from map_runtime_fixtures import save
from test_slurm_commands import guard

INPUTS = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/frontend-deployment-fixture-inputs"
)


def originals() -> dict[str, bytes]:
    old = served_originals()
    receipt = json.loads((INPUTS / "receipt.json").read_text())
    assert (
        receipt["passed"]
        and receipt["job_id"] == "4800560"
        and receipt["original_changes"] == 0
    )
    extra = {row["relative"]: row for row in receipt["files"]}
    result = {}
    for name, checksum in PINS.items():
        if name in extra:
            assert extra[name]["sha256"] == checksum
            path = INPUTS / name
            assert path.resolve(strict=True) == path
            body = path.read_bytes()
        else:
            body = old[Path(name).name]
        assert hashlib.sha256(body).hexdigest() == checksum
        result[name] = body
    return result


def inputs(root: Path) -> MapServiceSpec:
    spec = selected(root)
    plan = spec.inputs
    declaration = next(t for t in plan.trees if t.role == "frontend")
    raw = json.loads(Path(declaration.inventory_path).read_text())
    rows = {row["relative"]: row for row in raw["files"]}
    directories = set(raw["directories"])
    for name, body in originals().items():
        path = Path(declaration.source_root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(0o600)
        label = raw["source"] + "/" + name
        rows[name] = dict(
            relative=name,
            source=label,
            resolved_source=label,
            state=[1, 2, len(body), 3, 4, 0o600],
            sha256=hashlib.sha256(body).hexdigest(),
            bytes=len(body),
        )
        directories.update(str(p) for p in Path(name).parents if str(p) != ".")
    raw.update(
        files=list(rows.values()),
        directories=sorted(directories),
        bytes=sum(row["bytes"] for row in rows.values()),
    )
    pin = save(Path(declaration.inventory_path), raw)
    updated = MapRuntimeTree.model_validate(
        {**declaration.model_dump(), "inventory": pin}
    )
    receipt = json.loads(Path(plan.publication_path).read_text())
    row = next(r for r in receipt["trees"] if r["key"] == "frontend")
    row.update(
        files=len(rows),
        bytes=raw["bytes"],
        inventory=dict(path=declaration.inventory_path, sha256=pin.sha256),
    )
    plan = MapRuntimeInputs.model_validate(
        {
            **plan.model_dump(),
            "trees": tuple(updated if t.role == "frontend" else t for t in plan.trees),
            "publication": save(Path(plan.publication_path), receipt),
        }
    )
    return MapServiceSpec.model_validate({**spec.model_dump(), "inputs": plan})


def frontend_case(
    root: Path,
) -> tuple[MapServiceSpec, NativeMapFrontendFiles, MapFrontendPreparation]:
    spec = inputs(root)
    cloned(spec)
    files = NativeMapFrontendFiles()
    return spec, files, MapFrontendPreparation(spec, files)


@contextmanager
def prepared_generation(
    root: Path,
) -> Iterator[tuple[MapFrontendPreparation, MapGeneration, Commands, Group]]:
    spec, files, frontend = frontend_case(root)
    NativeMapLayout().prepare(
        spec, controls(spec, hostname="fixture-node", host_cpus=128), guard()
    )
    frontend.prepare(guard(60))
    commands, services = Commands(spec), Group(spec)
    generation = MapGeneration(spec, commands, services, BoundedMapStartupControls())
    try:
        yield frontend, generation, commands, services
    finally:
        for handle in services.sockets:
            handle.close()
