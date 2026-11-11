"""Read-only exact five-image native programs and controlled HTTP; no site data/DB."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import threading
import pytest
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.sites.map.service_readiness import HTTP_PROBE, POSTGRES_READY
from lab_generate_skill.sites.map.service_controls import SEARCH_ROUTER
from test_slurm_commands import guard

ROOT = Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/map")


@pytest.fixture(scope="module")
def images() -> dict[str, Path]:
    result = {}
    for role, (sha, size) in IMAGE_PINS.items():
        path = ROOT / role / sha / (role + ".sif")
        assert path.resolve(strict=True) == path and path.stat().st_size == size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for part in iter(lambda: stream.read(8 * 1024**2), b""):
                digest.update(part)
        assert digest.hexdigest() == sha
        result[role] = path
    return result


def base(image: Path) -> tuple[str, ...]:
    return (
        "/usr/bin/apptainer",
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/tmp",
        str(image),
    )


def test_original_native_image_programs_compile_without_services(
    images: dict[str, Path],
) -> None:
    commands = CheckedNativeCommands(ProcessRunner(max_output_bytes=8 * 1024**2))
    inputs = CheckedNativeInputCommands(ProcessRunner(max_output_bytes=65536))

    def execute(argv: tuple[str, ...]) -> bytes:
        try:
            return commands.run(argv, guard(30))
        except CommandFailure as error:
            print("original native failure", error.capture)
            raise

    for role, executable, expected in (
        ("db", "postgres", b"11."),
        ("nominatim", "/usr/lib/postgresql/14/bin/postgres", b"14."),
        ("tiles", "/usr/lib/postgresql/15/bin/postgres", b"15."),
    ):
        result = execute(base(images[role]) + (executable, "--version"))
        assert expected in result
        # Original PG11 dash executes -n -c strings; parse stdin instead and
        # prove it did not execute even the harmless leading sentinel.
        try:
            syntax = inputs.run_input(
                base(images[role]) + ("/bin/sh", "-n"),
                ("printf MUST_NOT_EXECUTE\n" + POSTGRES_READY).encode(),
                guard(30),
            )
        except CommandFailure as error:
            print("original native syntax failure", error.capture)
            raise
        assert syntax == b""
    with pytest.raises(CommandFailure) as invalid:
        inputs.run_input(
            base(images["db"]) + ("/bin/sh", "-n"), b"case in\n", guard(30)
        )
    assert (
        invalid.value.capture.returncode != 0
        and b"Syntax error" in invalid.value.capture.stderr
    )
    ruby = execute(base(images["web"]) + ("ruby", "-c", "-e", HTTP_PROBE))
    assert ruby.strip() == b"Syntax OK"
    execute(
        base(images["nominatim"])
        + ("php", "-r", "if(false){" + SEARCH_ROUTER.removeprefix("<?php") + "}"),
    )
    assert re.search(
        rb"[0-9]+\.[0-9]+",
        execute(base(images["osrm"]) + ("osrm-routed", "--version")),
    )


def test_actual_native_ruby_http_is_single_complete_request_and_no_retry_on_truncation(
    images: dict[str, Path],
) -> None:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(self.path)
            body = b"complete original body"
            self.send_response(200)
            self.send_header(
                "Content-Length",
                str(len(body) + (17 if self.path == "/truncated" else 0)),
            )
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    commands = CheckedNativeCommands(ProcessRunner(max_output_bytes=8 * 1024**2))
    args = base(images["web"]) + ("ruby", "-e", HTTP_PROBE, str(server.server_port))
    try:
        raw = commands.run(args + ("/complete", "2"), guard(30))
        value = json.loads(raw)
        assert value == {
            "status": 200,
            "body_base64": "Y29tcGxldGUgb3JpZ2luYWwgYm9keQ==",
        }
        with pytest.raises(CommandFailure) as caught:
            commands.run(args + ("/truncated", "2"), guard(30))
        capture = caught.value.capture
        assert caught.value.reason_code == "NATIVE_COMMAND_FAILED"
        assert capture.complete and capture.returncode != 0
        assert b"Incomplete original startup response" in capture.stderr
        assert capture.termination is not None and capture.termination.state == "reaped"
        assert not capture.termination.cleanup_errors
        assert seen == ["/complete", "/truncated"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()
