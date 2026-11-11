"""Startup request failure/cancellation and exact shared deadline composition."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.sites.map.service_readiness import HTTP_PROBE, POSTGRES_READY
from lab_generate_skill.domain.errors import InvalidTransition
from map_services_fixtures import generation_case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_pg_malformed_reply_prevents_http_and_namespace_pin(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.pg = b"not ready reply"
        with pytest.raises(ValueError):
            generation.start(guard())
        assert group.names == ["search_postgres"] and not generation.pins
        assert len(commands.calls) == 1 and POSTGRES_READY in commands.calls[0]
        generation.stop(guard())


def test_http_transport_error_is_original_and_not_reissued(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.fail = HTTP_PROBE
        with pytest.raises(OSError) as caught:
            generation.start(guard())
        assert (
            caught.value is commands.error
            and sum(HTTP_PROBE in c for c in commands.calls) == 1
        )
        assert generation.state == "failed"
        with pytest.raises(InvalidTransition):
            generation.start(guard())
        generation.stop(guard())


def test_cancellation_after_native_command_retains_started_handles(
    node_path: Path,
) -> None:
    with generation_case(node_path) as (generation, commands, group):

        class Cancel:
            def checkpoint(self) -> float:
                if commands.calls:
                    raise TimeoutError("original caller cancelled")
                return 600.0

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(TimeoutError):
            generation.start(Cancel())
        assert group.names == ["search_postgres"] and len(commands.calls) == 1
        assert generation.state == "failed"
        generation.stop(guard())


def test_connection_refused_probe_then_known_response(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.http = [b"waiting"]
        assert generation.start(guard(600)) == generation.spec.endpoint
        assert sum(HTTP_PROBE in c for c in commands.calls) == 8
        generation.stop(guard())


@pytest.mark.parametrize(
    "port,path,first,seconds",
    [
        (True, "/", False, 180),
        (12345, "/", False, 180),
        (12001, "//outside", False, 180),
        (12001, "/\n", False, 180),
        (12001, None, False, 180),
        (12001, "/", None, 180),
        (12001, "/", True, 30),
        (12002, "/", True, 180),
        (12001, "/", False, True),
    ],
)
def test_invalid_startup_request_precedes_native_effect(
    node_path: Path, port: Any, path: Any, first: Any, seconds: Any
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        with pytest.raises(ValueError):
            generation.health.http(
                port, path, guard(), first_rails=first, seconds=seconds
            )
        assert not commands.calls and not group.names


def test_deadline_port_never_extends_original_caller() -> None:
    controls = BoundedMapStartupControls()
    assert 0 < controls.bind(guard(0.5), "copy_modules").checkpoint() <= 0.5
    assert 0 < controls.bind(guard(600), "postgres_probe").checkpoint() <= 10
    invalid: Any = "other"
    with pytest.raises(ValueError):
        controls.bind(guard(), invalid)


@pytest.mark.parametrize(
    "endpoint,seconds,first,caller,limit",
    [
        ("tiles", 90, False, 600.0, 90.0),
        ("tiles", 30, False, 600.0, 30.0),
        ("tiles", 90, False, 0.5, 0.5),
        ("tiles", 30, False, 0.5, 0.5),
        ("web", 180, True, 600.0, 180.0),
        ("web", 180, True, 0.5, 0.5),
        ("search", 180, False, 600.0, 10.0),
        ("web", 90, False, 600.0, 10.0),
        ("tiles", 180, False, 600.0, 10.0),
    ],
)
def test_original_probe_phase_and_caller_budgets_are_both_respected(
    node_path: Path,
    endpoint: str,
    seconds: int,
    first: bool,
    caller: float,
    limit: float,
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        port = getattr(generation.spec.ports, endpoint)
        generation.health.http(
            port, "/", guard(caller), first_rails=first, seconds=seconds
        )
        assert len(commands.calls) == 1
        assert limit - 0.25 < float(commands.calls[0][-1]) <= limit
        assert not group.names
