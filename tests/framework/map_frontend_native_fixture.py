"""Controlled original-image Ruby frontend with real namespace/lease ownership.

Only Web SIF executes; SQL remains an explicit synthetic state port. This is not
Rails, a full Map deployment, a registered worker or an Actor task.
"""

import os
from pathlib import Path
import socket
from lab_generate_skill.domain.map_services import MapServiceSpec, MapPorts
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.local_ports import LocalPortLease
from lab_generate_skill.ports.map_services import MapStartupPhase
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.map_runtime.services import OwnedMapServices
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout
from lab_generate_skill.adapters.map_runtime.frontend import NativeMapFrontendFiles
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.map_runtime.frontend_transients import (
    NativeMapFrontendTransients,
)
from lab_generate_skill.adapters.network.loopback_ports import LoopbackPorts
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.combined_control import CombinedControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.sites.map.frontend import MapFrontendPreparation
from lab_generate_skill.sites.map.frontend_reset import MapFrontendReset
from lab_generate_skill.sites.map.state_guard import MapStateGuard
from lab_generate_skill.sites.map.service_controls import controls
from lab_generate_skill.sites.map.service_commands import container
from lab_generate_skill.sites.map.service_readiness import MapReadiness
from map_frontend_fixtures import inputs
from map_services_fixtures import cloned
from map_state_fixtures import SQL

PROGRAM = r"""
require 'socket'
port = Integer(ARGV.fetch(0))
mode = ARGV.fetch(1)
raise 'explicit fixture mode required' unless ['graceful', 'forced'].include?(mode)
server = TCPServer.new('127.0.0.1', port)
STDOUT.sync = true
Signal.trap('TERM') { exit 0 if mode == 'graceful' }
puts "CONTROLLED_FRONTEND_READY #{mode}"
loop do
  client = server.accept
  begin
    request = client.gets
    raise 'missing original request' if request.nil?
    while (line = client.gets)
      break if line == "\r\n"
    end
    body = 'controlled original-image frontend'
    client.write("HTTP/1.1 200 OK\r\nContent-Length: #{body.bytesize}\r\nConnection: close\r\n\r\n#{body}")
    puts 'COMPLETE_ORIGINAL_REQUEST'
  ensure
    client.close
  end
end
"""


class FixtureControls:
    """Shorten only the local grace in this fault fixture; production remains30s."""

    def bind(
        self, caller: OperationControl, phase: MapStartupPhase
    ) -> OperationControl:
        if phase == "frontend_grace":
            return CombinedControl(caller, DeadlineControl(0.25, "map-frontend_grace"))
        return BoundedMapStartupControls().bind(caller, phase)


class NativeFrontendFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.spec = inputs(root)
        self.lease: LocalPortLease | None = None
        self.services: OwnedMapServices | None = None
        self.limits = FixtureControls()
        self.commands = CheckedNativeCommands(
            ProcessRunner(max_output_bytes=8 * 1024**2, reap_timeout=2)
        )
        self.sql = SQL()
        self.reset: MapFrontendReset | None = None

    def initialize(self, mode: str, control: OperationControl) -> MapFrontendReset:
        if mode not in ("graceful", "forced"):
            raise ValueError("Exact native frontend fixture mode required")
        self.lease = LoopbackPorts().reserve(6, control)
        ports = self.lease.ports
        self.spec = MapServiceSpec(
            inputs=self.spec.inputs,
            ports=MapPorts(
                web=ports[0],
                search=ports[1],
                car=ports[2],
                bike=ports[3],
                foot=ports[4],
                tiles=ports[5],
            ),
        )
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
        MapFrontendPreparation(self.spec, NativeMapFrontendFiles()).prepare(control)
        image = next(i.file for i in self.spec.inputs.images if i.role == "web")
        source = (
            Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/map/web")
            / IMAGE_PINS["web"][0]
        )
        copy_pinned_file(
            source, Path(self.spec.inputs.files.node_root) / "image", image, control
        )
        app = Path(self.spec.inputs.node_tree("frontend"))
        for name, body in {
            "public/persistent": b"original persistent file",
            "storage/persistent": b"original storage",
            "tmp/cache/assets/sprockets/original": b"original compiled cache",
            "tmp/cache/old-session": b"delete",
            "tmp/pids/puma.pid": b"old original PID",
        }.items():
            path = app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (app / "public").chmod(0o700)
        self.commands.run(
            container(self.spec, "web") + ("ruby", "-c", "-e", PROGRAM), control
        )
        self.services = OwnedMapServices(
            Path(self.spec.inputs.files.log_root), self.limits
        )
        self.services.start(
            "rails_server",
            container(self.spec, "web")
            + ("ruby", "-e", PROGRAM, str(self.spec.ports.web), mode),
            control,
        )
        MapReadiness(self.spec, self.commands, self.services, self.limits).http(
            self.spec.ports.web, "/", control, first_rails=True
        )
        self.services.pin_namespace("rails_server", control)
        tracker = MapStateGuard(
            self.spec, self.sql, NativeMapPersistentFiles(), self.services, self.limits
        )
        tracker.install(control)
        self.reset = MapFrontendReset(
            self.spec,
            tracker,
            self.services,
            NativeMapFrontendTransients(),
            self.commands,
            self.limits,
        )
        return self.reset
