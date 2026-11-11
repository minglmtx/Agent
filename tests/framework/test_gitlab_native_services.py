"""Native service/health/stop contracts, using explicit fake original effects."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.gitlab.service_contract import (
    GitlabPorts,
    GitlabServiceSpec,
)
from lab_generate_skill.sites.gitlab.service_commands import (
    container,
    service_commands,
    SERVICE_NAMES,
)
from lab_generate_skill.sites.gitlab.service_programs import (
    CONFIGURE,
    HTTP_READY,
    BACKEND_READY,
)
from lab_generate_skill.sites.gitlab.services import (
    seed,
    GitlabGeneration,
    require_stop,
)
from gitlab_native_fixtures import spec, Commands, Group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def setup(root: Path) -> tuple[GitlabGeneration, Commands, Group]:
    (root / "state").mkdir()
    (root / "control").mkdir()
    commands = Commands(root)
    group = Group()
    seed(spec(root), commands, guard())
    return GitlabGeneration(spec(root), commands, group), commands, group


def test_original_services_config_health_and_all_held_pins(node_path: Path) -> None:
    generation, commands, group = setup(node_path)
    assert generation.start(guard()) == "http://127.0.0.1:12001/"
    assert (
        group.names == list(SERVICE_NAMES)
        and tuple(x.service for x in generation.pins) == SERVICE_NAMES
    )
    actual = [x for x in commands.calls if CONFIGURE in x and x[-1] != CONFIGURE]
    assert len(actual) == 1 and actual[0][-3:] == ("12001", "12002", "native_user")
    assert any(BACKEND_READY in x for x in commands.calls) and any(
        HTTP_READY in x for x in commands.calls
    )
    argv = service_commands(spec(node_path))
    assert "listen_addresses=" in argv["postgres"]
    assert argv["redis"][-2:] == ("--port", "0")
    assert (
        "unix" in argv["workhorse-internal"] and "127.0.0.1:12001" in argv["workhorse"]
    )
    assert "/control:ro" in " ".join(container(spec(node_path)))
    assert ":/snapshot:ro" in " ".join(container(spec(node_path), snapshot="read"))
    assert "HOME|PYTHONPATH" in (node_path / "control/service.sh").read_text()
    generation.confirm_healthy(guard())
    stopped = generation.quiesce(guard())
    require_stop(stopped, generation.pins)
    for call in (generation.start, generation.quiesce, generation.confirm_healthy):
        with pytest.raises(RuntimeError):
            call(guard())
    generation.stop(guard())
    assert group.stopped


@pytest.mark.parametrize(
    "failure", [*SERVICE_NAMES, "pin-postgres", "pin-workhorse", "quiesce"]
)
def test_partial_service_or_stop_retains_original_handles(
    node_path: Path, failure: str
) -> None:
    generation, commands, group = setup(node_path)
    group.fail = failure
    if failure == "quiesce":
        generation.start(guard())
        with pytest.raises(TimeoutError):
            generation.quiesce(guard())
    else:
        with pytest.raises(OSError):
            generation.start(guard())
    assert generation.state == "failed"
    generation.stop(guard())
    assert group.stopped


@pytest.mark.parametrize("phase", ["health", "cancel"])
def test_malformed_health_and_cancel_after_start_do_not_retry(
    node_path: Path, phase: str
) -> None:
    generation, commands, group = setup(node_path)
    if phase == "health":
        commands.health = b"not-a-health-state"
    else:
        commands.error = HTTP_READY
        commands.failure = OperationStopped("CANCELLED", "query")
    with pytest.raises((ValueError, OperationStopped)):
        generation.start(guard())
    assert generation.state == "failed"
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        generation.start(guard())
    assert len(commands.calls) == count
    commands.error = None
    generation.stop(guard())
    assert group.stopped


@pytest.mark.parametrize("code", [-9, 1, 143])
def test_abnormal_database_or_redis_stop_denies_copy(
    node_path: Path, code: int
) -> None:
    generation, commands, group = setup(node_path)
    generation.start(guard())
    group.exitcode = code
    with pytest.raises(ValueError):
        generation.quiesce(guard())
    assert generation.quiescence is not None and generation.state == "failed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("web", True),
        ("web", 1023),
        ("web", 65536),
        ("web", "12001"),
        ("metrics", 12001),
    ],
)
def test_invalid_endpoint_types_before_native_effect(field: str, value: Any) -> None:
    values: dict[str, Any] = dict(web=12001, metrics=12002)
    values[field] = value
    with pytest.raises(ValueError):
        GitlabPorts(**values)


def test_dirty_seed_invalid_mount_and_peer_identity_do_not_start_commands(
    node_path: Path,
) -> None:
    (node_path / "state").mkdir()
    (node_path / "state/old").write_text("original")
    commands = Commands(node_path)
    with pytest.raises(ValueError):
        seed(spec(node_path), commands, guard())
    assert not commands.calls
    bad: Any = "unknown"
    with pytest.raises(ValueError):
        container(spec(node_path), snapshot=bad)
    values = spec(node_path).model_dump()
    values["database_peer_user"] = "foreign\nentry"
    with pytest.raises(ValueError):
        GitlabServiceSpec.model_validate(values)


@pytest.mark.parametrize("failure", ["compiler_runs", "preflight_writes"])
def test_native_compiler_cannot_start_seed_or_services(
    node_path: Path, failure: str
) -> None:
    (node_path / "state").mkdir()
    (node_path / "control").mkdir()
    commands = Commands(node_path)
    if failure == "compiler_runs":
        commands.noexec_reply = b"native_noexec_marker"
    else:
        commands.preflight_writes = True
    with pytest.raises(ValueError):
        seed(spec(node_path), commands, guard())
    assert not any(
        "-e" in call and "/control/seed.sh" in call for call in commands.calls
    )
    assert not (node_path / "state/original").exists()
