"""Execute fixed PHP health code against a delayed local HTTP fixture, no site seed."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import hashlib
import json
import os
from pathlib import Path
from test_generator_step_live import command_json
import time
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.sites.shopping_admin.service_programs import HEALTH
from test_admin_database_native import IMAGE


def command(port: int, budget: str) -> tuple[str, ...]:
    return (
        "/usr/bin/apptainer",
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        str(IMAGE),
        "php",
        "-r",
        HEALTH,
        "frontend",
        str(port),
        budget,
    )


@pytest.mark.parametrize("budget", ["", "0", "-1", "nan", "inf", "86401", "bad"])
def test_frontend_rejects_invalid_native_budget(budget: str) -> None:
    if budget == "":
        with pytest.raises(ValueError, match="exact argv"):
            ProcessRunner().run(
                command(12001, budget), DeadlineControl(15, "empty-budget")
            )
        return
    result = ProcessRunner().run(
        command(12001, budget), DeadlineControl(15, "bad-health-budget")
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / (
            "health-invalid-"
            + hashlib.sha256(budget.encode()).hexdigest()[:12]
            + ".json"
        )
    ).write_text(json.dumps(command_json(result), indent=2) + "\n")
    assert result.complete and result.returncode == 64
    assert b"Invalid frontend health budget" in result.stderr


@pytest.mark.parametrize(
    "budget,expected,paths",
    [
        ("10", b"ready", ["/admin", "/login"]),
        ("0.3", b"waiting", ["/admin"]),
        ("4.5", b"waiting", ["/admin", "/login"]),
    ],
)
def test_slow_frontend_uses_one_shared_budget(
    budget: str, expected: bytes, paths: list[str]
) -> None:
    stopped = threading.Event()
    observed: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            observed.append(self.path)
            # The first response exceeds the previous three-second cutoff.
            if stopped.wait(4 if self.path == "/admin" else 1):
                return
            try:
                if self.path == "/admin":
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Admin login")
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the deliberately short budget expires.

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = time.monotonic()
        result = ProcessRunner().run(
            command(server.server_port, budget), DeadlineControl(15, "frontend-health")
        )
        elapsed = time.monotonic() - started
        assert result.complete and result.returncode == 0
        assert result.stdout == expected and observed == paths
        assert elapsed < 15
        if expected == b"ready":
            assert elapsed >= 5
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
