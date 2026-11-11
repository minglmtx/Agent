"""Controlled local HTTP and original published Ruby; no native Map services/DB."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from lab_generate_skill.adapters.map_runtime.metadata import read_pinned_bytes
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.service_readiness import HTTP_PROBE
from map_source_inputs import RUNTIME_PATH, RUNTIME_PIN
from test_slurm_commands import guard

BODY = b"\x89PNG\r\n\x1a\n" + b"controlled-complete-startup-tile" * 50


@dataclass
class ProbeServer:
    port: int = 0
    calls: list[str] = field(default_factory=list)
    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)


@contextmanager
def probe_server(mode: str) -> Iterator[ProbeServer]:
    if mode not in ("cold", "blocked", "partial", "redirect"):
        raise ValueError("Explicit controlled HTTP mode required")
    state = ProbeServer()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            state.calls.append(self.path)
            state.entered.set()
            if mode == "cold":
                state.release.wait(11.0)
            elif mode == "blocked":
                state.release.wait(30.0)
            self.send_response(302 if mode == "redirect" else 200)
            self.send_header("Content-Length", str(len(BODY)))
            self.send_header("Location", "/must-not-follow")
            self.end_headers()
            try:
                self.wfile.write(BODY[:8] if mode == "partial" else BODY)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.port = server.server_port
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield state
    finally:
        state.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


class OriginalRubyProbe:
    """Execute the exact production script, substituting only its image mount."""

    def __init__(self) -> None:
        raw = read_pinned_bytes(RUNTIME_PATH, RUNTIME_PIN, guard())
        inputs = MapRuntimeInputs.model_validate_json(raw)
        image = next(i for i in inputs.images if i.role == "web")
        self.image = Path(image.source_path)
        assert (
            self.image.is_absolute()
            and self.image.stat().st_size == image.file.size_bytes
        )
        self.calls: list[tuple[str, ...]] = []
        self.native = CheckedNativeCommands(ProcessRunner())

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        index = argv.index("ruby")
        assert argv[index + 1 : index + 3] == ("-e", HTTP_PROBE)
        self.calls.append(argv)
        return self.native.run(
            (
                "/usr/bin/apptainer",
                "exec",
                "--containall",
                "--cleanenv",
                str(self.image),
            )
            + argv[index:],
            control,
        )
