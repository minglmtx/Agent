"""Synthetic native commands/processes; real published metadata and private files."""

import base64
from contextlib import contextmanager
from collections.abc import Iterator
import hashlib
import json
from pathlib import Path
import socket
from typing import Any
from lab_generate_skill.domain.map_services import MapServiceSpec, MapPorts
from lab_generate_skill.domain.map_runtime_inputs import (
    MapRuntimeInputs,
    MapRuntimeTree,
    MapTreeRole,
)
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.map_runtime.read_inputs import PublishedMapInputs
from lab_generate_skill.adapters.map_runtime.tree_copy import clone_tree
from lab_generate_skill.sites.map.service_controls import controls
from lab_generate_skill.sites.map.service_commands import setup_commands
from lab_generate_skill.sites.map.service_readiness import POSTGRES_READY, HTTP_PROBE
from lab_generate_skill.sites.map.services import MapGeneration
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.native_services import NativeServiceExit
from map_runtime_fixtures import runtime_case, save
from shopping_services_fixtures import Group as BaseGroup
from test_slurm_commands import guard

STYLE = b'<Map><Layer><Datasource><Parameter name="type">postgis</Parameter><Parameter name="host">original</Parameter><Parameter name="port">5432</Parameter><Parameter name="password">test-only</Parameter><Parameter name="table">(select * from planet_osm_point) as data</Parameter></Datasource></Layer></Map>'
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-png-body" * 100


def replace_source(
    plan: MapRuntimeInputs, role: MapTreeRole, name: str, body: bytes
) -> MapRuntimeInputs:
    declaration = next(t for t in plan.trees if t.role == role)
    path = Path(declaration.source_root) / name
    path.write_bytes(body)
    raw = json.loads(Path(declaration.inventory_path).read_text())
    row = next(r for r in raw["files"] if r["relative"] == name)
    raw["bytes"] += len(body) - row["bytes"]
    row.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    row["state"][2] = len(body)
    pin = save(Path(declaration.inventory_path), raw)
    updated = MapRuntimeTree.model_validate(
        {**declaration.model_dump(), "inventory": pin}
    )
    receipt = json.loads(Path(plan.publication_path).read_text())
    entry = next(r for r in receipt["trees"] if r["key"] == role)
    entry["bytes"] = raw["bytes"]
    entry["inventory"]["sha256"] = pin.sha256
    return MapRuntimeInputs.model_validate(
        {
            **plan.model_dump(),
            "trees": tuple(updated if t.role == role else t for t in plan.trees),
            "publication": save(Path(plan.publication_path), receipt),
        }
    )


def selected(root: Path) -> MapServiceSpec:
    plan = runtime_case(root)
    versions: tuple[tuple[MapTreeRole, str], ...] = (
        ("app", "11"),
        ("search", "14"),
        ("tiles", "15"),
    )
    for role, version in versions:
        plan = replace_source(
            plan, role, "postgres/PG_VERSION", (version + "\n").encode()
        )
    metadata = dict(
        status="complete",
        postgres_version="11",
        full_snapshot_imported=True,
        object_checks={
            kind: dict(http_status=200, has_object_id=True, id=123)
            for kind in ("node", "way")
        },
    )
    plan = replace_source(plan, "app", "baseline.json", json.dumps(metadata).encode())
    return MapServiceSpec(
        inputs=plan,
        ports=MapPorts(
            web=12001, search=12002, car=12003, bike=12004, foot=12005, tiles=12006
        ),
    )


def cloned(spec: MapServiceSpec) -> None:
    root = Path(spec.inputs.files.node_root)
    root.mkdir(mode=0o700)
    for name in ("state", "input", "image", "logs"):
        (root / name).mkdir(mode=0o700)
    for declaration, inventory in zip(
        spec.inputs.trees, PublishedMapInputs().read(spec.inputs, guard()), strict=True
    ):
        clone_tree(
            declaration,
            inventory,
            Path(spec.inputs.node_tree(declaration.role)),
            guard(),
        )


class Group(BaseGroup):
    def __init__(self, spec: MapServiceSpec) -> None:
        super().__init__()
        self.spec = spec
        self.sockets: list[socket.socket] = []
        self.socket_kind = "socket"
        self.masters: dict[str, int] = {}

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        super().start(name, argv, control)
        self.masters[name] = 1000 + self.names.index(name) * 10
        if name == "renderd":
            path = Path(self.spec.state_root("tiles")) / "run/renderd.sock"
            if self.socket_kind == "file":
                path.write_bytes(b"not socket")
            else:
                handle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sockets.append(handle)
                handle.bind(str(path))

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        super().stop(control)
        for handle in self.sockets:
            handle.close()
        return tuple(
            NativeServiceExit(
                service=name,
                process_id=pid,
                returncode=0,
                state="reaped",
                kill_requested=False,
            )
            for name, pid in self.masters.items()
        )


class Commands:
    def __init__(self, spec: MapServiceSpec) -> None:
        self.spec = spec
        self.calls: list[tuple[str, ...]] = []
        self.fail: str | None = None
        self.http: list[bytes] = []
        self.pg = b"ready"
        self.png = PNG
        self.error = OSError("original native command failed")

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        setups = setup_commands(self.spec)
        if self.fail is not None and (
            self.fail in argv or (self.fail in setups and argv == setups[self.fail])
        ):
            raise self.error
        if argv == setups["copy_style"]:
            (Path(self.spec.state_root("tiles")) / "style").mkdir()
        if argv == setups["compile_style"]:
            (Path(self.spec.state_root("tiles")) / "style/mapnik.xml").write_bytes(
                STYLE
            )
        if POSTGRES_READY in argv:
            return self.pg
        if HTTP_PROBE in argv:
            if self.http:
                return self.http.pop(0)
            body = (
                self.png if argv[-3] == str(self.spec.ports.tiles) else b"native ready"
            )
            return json.dumps(
                dict(status=200, body_base64=base64.b64encode(body).decode())
            ).encode()
        return b""


@contextmanager
def generation_case(root: Path) -> Iterator[tuple[MapGeneration, Commands, Group]]:
    spec = selected(root)
    cloned(spec)
    NativeMapLayout().prepare(
        spec, controls(spec, hostname="fixture-node", host_cpus=128), guard()
    )
    commands, services = Commands(spec), Group(spec)
    generation = MapGeneration(spec, commands, services, BoundedMapStartupControls())
    try:
        yield generation, commands, services
    finally:
        for handle in services.sockets:
            handle.close()
