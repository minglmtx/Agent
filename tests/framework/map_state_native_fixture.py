"""Tiny PG11 fixture with original DB image/commands, no benchmark database."""

from pathlib import Path
import shutil
import socket
import os
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.service_commands import container, service_commands
from lab_generate_skill.sites.map.service_controls import controls
from lab_generate_skill.sites.map.service_readiness import MapReadiness
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from map_services_fixtures import selected, cloned

SCHEMA = b"""CREATE TABLE users(id bigserial PRIMARY KEY, name text);
CREATE TABLE notes(id bigserial PRIMARY KEY, body text);
CREATE TABLE inserted(id integer PRIMARY KEY);
CREATE TABLE updated(id integer PRIMARY KEY);
CREATE TABLE deleted(id integer PRIMARY KEY);
CREATE TABLE truncated(id integer PRIMARY KEY);
INSERT INTO users(name) VALUES ('original');
INSERT INTO notes(body) VALUES ('original');
INSERT INTO updated VALUES (1);
INSERT INTO deleted VALUES (1);
INSERT INTO truncated VALUES (1);
"""


class TinyMapNative:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.spec = selected(root)
        self.runner = ProcessRunner(max_output_bytes=4 * 1024**2, reap_timeout=2)
        self.commands = CheckedNativeCommands(self.runner)
        self.inputs = CheckedNativeInputCommands(self.runner)
        self.limits = BoundedMapStartupControls()
        self.services: LocalNativeServices | None = None
        self.tracker: MapStateGuard | None = None

    def initialize(self, control: OperationControl) -> MapStateGuard:
        cloned(self.spec)
        NativeMapLayout().prepare(
            self.spec,
            controls(
                self.spec,
                hostname=socket.gethostname(),
                host_cpus=os.sysconf("SC_NPROCESSORS_ONLN"),
            ),
            control,
        )
        app = Path(self.spec.inputs.node_tree("frontend"))
        for name in ("storage", "public"):
            (app / name).mkdir(mode=0o700)
        (app / "public/original.txt").write_bytes(b"small native fixture\n")
        image = next(i.file for i in self.spec.inputs.images if i.role == "db")
        source = (
            Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/map/db")
            / IMAGE_PINS["db"][0]
        )
        copy_pinned_file(
            source, Path(self.spec.inputs.files.node_root) / "image", image, control
        )
        # Only these deliberately synthetic stub bytes are replaced by initdb.
        # No published/full Map DB is read, deleted or initialized by this fixture.
        pg = Path(self.spec.inputs.node_tree("app")) / "postgres"
        assert sorted(str(p.relative_to(pg)) for p in pg.rglob("*") if p.is_file()) == [
            "PG_VERSION",
            "global/pg_control",
        ]
        shutil.rmtree(pg)
        pg.mkdir(mode=0o700)
        self.commands.run(
            container(self.spec, "db")
            + (
                "initdb",
                "-D",
                "/state/pg",
                "-U",
                "openstreetmap",
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
            ),
            control,
        )
        self.services = LocalNativeServices(Path(self.spec.inputs.files.log_root))
        self.services.start(
            "app_postgres", service_commands(self.spec)["app_postgres"], control
        )
        MapReadiness(self.spec, self.commands, self.services, self.limits).postgres(
            "db", control
        )
        self.services.pin_namespace("app_postgres", control)
        self.commands.run(
            container(self.spec, "db")
            + (
                "createdb",
                "-h",
                "/state/run",
                "-U",
                "openstreetmap",
                "openstreetmap",
            ),
            control,
        )
        self.sql(SCHEMA, control)
        self.tracker = MapStateGuard(
            self.spec,
            self.inputs,
            NativeMapPersistentFiles(),
            self.services,
            self.limits,
        )
        return self.tracker

    def sql(self, data: bytes, control: OperationControl) -> bytes:
        return self.inputs.run_input(
            container(self.spec, "db")
            + (
                "psql",
                "-XAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "/state/run",
                "-U",
                "openstreetmap",
                "-d",
                "openstreetmap",
            ),
            data,
            control,
        )
