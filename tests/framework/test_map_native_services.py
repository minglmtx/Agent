"""Ten-service dependency composition with explicit synthetic native ports."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.sites.map.service_commands import (
    SERVICE_NAMES,
    service_commands,
    setup_commands,
    container,
)
from lab_generate_skill.sites.map.service_readiness import HTTP_PROBE, POSTGRES_READY
from lab_generate_skill.sites.map.service_controls import controls, sample_tile_path
from map_services_fixtures import generation_case, selected, PNG
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_actual_small_layout_to_ten_service_ports_and_owned_stop(
    node_path: Path,
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        assert generation.start(guard(600)) == generation.spec.endpoint
        assert (
            group.names == list(SERVICE_NAMES)
            and tuple(p.service for p in generation.pins) == SERVICE_NAMES
        )
        assert generation.tile_sample == PNG
        http = [c for c in commands.calls if HTTP_PROBE in c]
        assert len(http) == 7
        assert [c[-2] for c in http].count(sample_tile_path()) == 2
        assert http[-1][-2] == "/" and 179 < float(http[-1][-1]) <= 180
        assert all(float(c[-1]) <= 10 for c in http[:-3])
        assert 89 < float(http[-3][-1]) <= 90
        assert 29 < float(http[-2][-1]) <= 30
        assert sum(POSTGRES_READY in c for c in commands.calls) == 3
        assert all(
            commands.calls.count(c) == 1
            for c in setup_commands(generation.spec).values()
        )
        style = (
            Path(generation.spec.state_root("tiles")) / "style/mapnik.xml"
        ).read_text()
        assert (
            "/state/run" in style
            and "planet_osm_point" in style
            and "password" not in style
        )
        with pytest.raises(InvalidTransition):
            generation.start(guard())
        facts = generation.stop(guard())
        assert generation.state == "stopped" and group.stopped and len(facts) == 10
        with pytest.raises(InvalidTransition):
            generation.start(guard())


@pytest.mark.parametrize(
    "failure", [*SERVICE_NAMES, "pin-search_postgres", "pin-rails_server"]
)
def test_partial_service_failure_retains_original_handles_no_restart(
    node_path: Path, failure: str
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        group.fail = failure
        with pytest.raises(OSError):
            generation.start(guard(600))
        assert generation.state == "failed" and group.names
        before = list(group.names)
        with pytest.raises(InvalidTransition):
            generation.start(guard())
        assert group.names == before
        generation.stop(guard())
        assert group.stopped


@pytest.mark.parametrize(
    "failure",
    [
        "search_refresh",
        "copy_style",
        "compile_style",
        "apache_check",
        "copy_modules",
        "bundle_check",
    ],
)
def test_original_setup_failure_not_reissued(node_path: Path, failure: str) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.fail = failure
        with pytest.raises(OSError) as caught:
            generation.start(guard(600))
        assert caught.value is commands.error and generation.state == "failed"
        assert commands.calls.count(setup_commands(generation.spec)[failure]) == 1
        with pytest.raises(InvalidTransition):
            generation.start(guard())
        generation.stop(guard())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"null",
        b"{}",
        b'{"status":true,"body_base64":""}',
        b'{"status":200,"body_base64":"!!"}',
        b'{"status":503,"body_base64":""}',
    ],
)
def test_http_unknown_or_error_stops_before_routes_without_reprobe(
    node_path: Path, raw: bytes
) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.http = [raw]
        with pytest.raises(ValueError):
            generation.start(guard(600))
        assert group.names == ["search_postgres", "search_http"]
        assert sum(HTTP_PROBE in c for c in commands.calls) == 1
        assert generation.state == "failed"
        generation.stop(guard())


def test_wrong_renderd_socket_and_bad_png_stop_before_app(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        group.socket_kind = "file"
        with pytest.raises(ValueError, match="Unix socket"):
            generation.start(guard(600))
        assert "tile_http" not in group.names and "app_postgres" not in group.names
        generation.stop(guard())


def test_invalid_tile_body_preserved_before_app(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        commands.png = b"bad native tile body"
        with pytest.raises(ValueError, match="tile/cache"):
            generation.start(guard(600))
        assert (
            generation.tile_sample == commands.png and "app_postgres" not in group.names
        )
        generation.stop(guard())


def test_foreign_owner_rejected_before_any_native_effect(node_path: Path) -> None:
    with generation_case(node_path) as (generation, commands, group):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(generation.start, guard()).result()
        assert generation.state == "new" and not group.names and not commands.calls


def test_commands_only_use_original_private_mounts_and_fixed_native_versions(
    node_path: Path,
) -> None:
    spec = selected(node_path)
    argv = service_commands(spec)
    assert tuple(argv) == SERVICE_NAMES
    for command in argv.values():
        assert command[:2] == ("/usr/bin/apptainer", "exec")
        assert "--containall" in command and "--cleanenv" in command
        assert not any(spec.inputs.files.workspace_root in a for a in command)
    assert "/usr/lib/postgresql/14/bin/postgres" in argv["search_postgres"]
    assert "/usr/lib/postgresql/15/bin/postgres" in argv["tile_postgres"]
    assert spec.inputs.node_image("db") in argv["app_postgres"]
    assert "WEB_CONCURRENCY=0" in argv["rails_server"]
    assert not any("initdb" in c or "db:migrate" in c for c in argv.values())
    assert spec.inputs.node_tree("routing") + ":/data:ro" in argv["route_car"]
    invalid_flag: Any = None
    with pytest.raises(ValueError):
        container(spec, "db", app=invalid_flag)
    with pytest.raises(ValueError):
        container(spec, "db", app=True)
    with pytest.raises(ValueError):
        container(spec, "web", apache=True)
