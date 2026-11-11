"""Pinned Ruby single-request startup budgets, complete bytes and failed reads."""

from pathlib import Path
import threading
import pytest
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.map_services import MapPorts
from lab_generate_skill.sites.map.service_readiness import MapReadiness
from map_services_fixtures import Group, selected
from map_startup_probe_fixtures import BODY, OriginalRubyProbe, probe_server
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_cold_tile_headers_after_ten_seconds_use_original_phase_once(
    node_path: Path,
) -> None:
    with probe_server("cold") as server:
        spec = selected(node_path)
        spec = spec.model_copy(
            update={
                "ports": MapPorts(**{**spec.ports.model_dump(), "tiles": server.port})
            }
        )
        commands = OriginalRubyProbe()
        readiness = MapReadiness(
            spec, commands, Group(spec), BoundedMapStartupControls()
        )
        body = readiness.http(server.port, "/tile/original.png", guard(40), seconds=90)
        assert body == BODY and readiness.last_http == (200, BODY)
        assert server.calls == ["/tile/original.png"] and len(commands.calls) == 1
        assert 10 < float(commands.calls[0][-1]) <= 40


@pytest.mark.parametrize("mode", ["partial", "redirect"])
def test_original_ruby_partial_or_redirect_never_reissues(
    node_path: Path, mode: str
) -> None:
    with probe_server(mode) as server:
        spec = selected(node_path)
        spec = spec.model_copy(
            update={
                "ports": MapPorts(**{**spec.ports.model_dump(), "tiles": server.port})
            }
        )
        commands = OriginalRubyProbe()
        readiness = MapReadiness(
            spec, commands, Group(spec), BoundedMapStartupControls()
        )
        if mode == "partial":
            with pytest.raises(CommandFailure) as caught:
                readiness.http(server.port, "/tile/original.png", guard(20), seconds=90)
            assert (
                caught.value.capture.complete and caught.value.capture.returncode == 1
            )
            assert (
                b"Incomplete original startup response" in caught.value.capture.stderr
            )
        else:
            with pytest.raises(ValueError, match="did not complete with 200"):
                readiness.http(server.port, "/tile/original.png", guard(20), seconds=90)
            assert readiness.last_http == (302, BODY)
        assert server.calls == ["/tile/original.png"] and len(commands.calls) == 1


def test_cancel_inflight_original_ruby_read_has_one_request_and_reaped_child(
    node_path: Path,
) -> None:
    with probe_server("blocked") as server:
        spec = selected(node_path)
        spec = spec.model_copy(
            update={
                "ports": MapPorts(**{**spec.ports.model_dump(), "tiles": server.port})
            }
        )
        commands = OriginalRubyProbe()
        cancelled = threading.Event()

        class CancelAfterRequest:
            def checkpoint(self) -> float:
                if cancelled.is_set():
                    raise OperationStopped("CANCELLED", "original-startup-probe")
                return 20.0

            def wait(self, seconds: float) -> None:
                cancelled.wait(seconds)
                self.checkpoint()

        def cancel() -> None:
            if server.entered.wait(15):
                cancelled.set()

        thread = threading.Thread(target=cancel)
        thread.start()
        try:
            readiness = MapReadiness(
                spec, commands, Group(spec), BoundedMapStartupControls()
            )
            with pytest.raises(CommandFailure) as caught:
                readiness.http(
                    server.port, "/tile/original.png", CancelAfterRequest(), seconds=90
                )
            assert caught.value.reason_code == "CANCELLED"
            assert caught.value.capture.termination is not None
            assert caught.value.capture.termination.state == "reaped"
            assert not caught.value.capture.complete
            assert server.calls == ["/tile/original.png"] and len(commands.calls) == 1
        finally:
            thread.join(timeout=16)
            assert not thread.is_alive()
