"""Original five-service setup, explicit restart, graceful gate and failures."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.sites.shopping.service_commands import (
    container,
    service_commands,
)
from lab_generate_skill.sites.shopping.service_contract import ShoppingPorts
from lab_generate_skill.sites.shopping.service_programs import CONFIGURE
from lab_generate_skill.sites.shopping.services import (
    ShoppingGeneration,
    SERVICE_NAMES,
    seed,
)
from shopping_services_fixtures import spec, Commands, Group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def setup(root: Path) -> tuple[ShoppingGeneration, Commands, Group]:
    for name in ("state", "control", "runtime"):
        (root / name).mkdir()
    commands, group = Commands(root), Group()
    seed(spec(root), commands, guard())
    return ShoppingGeneration(spec(root), commands, group), commands, group


def test_native_prepare_start_and_all_original_writer_pins(node_path: Path) -> None:
    generation, commands, group = setup(node_path)
    assert generation.start(guard(), configure=True) == "http://127.0.0.1:12001/"
    assert group.names == list(SERVICE_NAMES)
    assert tuple(x.service for x in group.pins) == SERVICE_NAMES
    config = [x for x in commands.calls if CONFIGURE in x][0]
    assert config[-4:] == ("12002", "12003", "12001", "12004")
    search = (node_path / "state/search/config/elasticsearch.yml").read_text()
    assert "cluster.name: native" in search and search.count("http.port:") == 1
    argv = service_commands(spec(node_path))
    assert "--init-file" not in " ".join(argv["mysql"])
    assert "900 1" in argv["redis"] and "--cleanenv" in argv["redis"]
    assert "/control:ro" in " ".join(container(spec(node_path)))
    fpm = (node_path / "control/php.conf").read_text()
    assert (node_path / "control/fastcgi_params").read_bytes() == (
        node_path / "state/fastcgi_params"
    ).read_bytes()
    assert "/state/var/session" in fpm and "/state/mail-outbox" not in fpm
    stopped = generation.quiesce(guard())
    assert all(x.returncode == 0 for x in stopped.masters)
    for call in (
        lambda: generation.start(guard(), configure=False),
        lambda: generation.quiesce(guard()),
    ):
        with pytest.raises(RuntimeError):
            call()
    generation.stop(guard())
    assert group.stopped


@pytest.mark.parametrize(
    "failure", [*SERVICE_NAMES, "pin-mysql", "pin-nginx", "quiesce"]
)
def test_partial_start_or_stop_retains_original_group(
    node_path: Path, failure: str
) -> None:
    generation, commands, group = setup(node_path)
    group.fail = failure
    if failure == "quiesce":
        generation.start(guard(), configure=False)
        with pytest.raises(TimeoutError):
            generation.quiesce(guard())
    else:
        with pytest.raises(OSError):
            generation.start(guard(), configure=False)
    assert generation.state == "failed"
    assert not any(CONFIGURE in x for x in commands.calls)
    generation.stop(guard())
    assert group.stopped


@pytest.mark.parametrize("code", [-9, 1, 143])
def test_abnormal_mysql_exit_denies_snapshot(node_path: Path, code: int) -> None:
    generation, commands, group = setup(node_path)
    generation.start(guard(), configure=False)
    group.exitcode = code
    with pytest.raises(ValueError, match="Abnormal"):
        generation.quiesce(guard())
    assert generation.state == "failed" and generation.quiescence is not None


@pytest.mark.parametrize(
    "field,value",
    [("web", True), ("web", 1023), ("web", 65536), ("web", "12000"), ("redis", 12001)],
)
def test_invalid_ports_before_effect(field: str, value: Any) -> None:
    data: dict[str, Any] = dict(
        web=12001, database=12002, redis=12003, search=12004, transport=12005
    )
    data[field] = value
    with pytest.raises(ValueError):
        ShoppingPorts(**data)
