"""Private startup contract, fixed service addresses and failure ownership."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.service_contract import (
    AdminPorts,
    AdminServiceSpec,
)
from lab_generate_skill.sites.shopping_admin.services import AdminLocalServices
from lab_generate_skill.sites.shopping_admin.service_commands import service_commands
from lab_generate_skill.sites.shopping_admin.service_programs import (
    CONFIGURE,
    HEALTH,
    SEED,
)
from site_instance_fixtures import node_path as node_path
from lab_generate_skill.sites.shopping_admin.database_observer_program import (
    DATABASE_OBSERVER_INIT_PHP,
)
from lab_generate_skill.sites.shopping_admin.drain_program import DATABASE_DRAIN_PHP
from test_admin_database import layout
from test_slurm_commands import guard


def spec(root: Path) -> AdminServiceSpec:
    return AdminServiceSpec(
        layout=layout(
            node_root=str(root),
            state_root=str(root / "state"),
            image_path=str(root / "image.sif"),
        ),
        ports=AdminPorts(
            web=12001, database=12002, redis=12003, search=12004, transport=12005
        ),
    )


class Commands:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, ...]] = []
        self.health = b"ready"
        self.config = b"configured"
        self.error: BaseException | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error:
            raise self.error
        if SEED in argv:
            target = self.root / "state/elasticsearch/config"
            target.mkdir(parents=True)
            (target / "elasticsearch.yml").write_text(
                "cluster.name: original\nhttp.port: 9200\n"
            )
        if DATABASE_OBSERVER_INIT_PHP in argv:
            return b"observer-configured"
        if DATABASE_DRAIN_PHP in argv:
            return b'{"other_sql_connections":0,"sql_transactions":0}'
        if HEALTH in argv:
            return self.health
        return self.config if CONFIGURE in argv else b""


from frontend_fixtures import namespace, stopped
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)


class Services:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.stopped = False
        self.pins: list[str] = []
        self.closed_namespaces: list[str] = []
        self.fail: str | None = None

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        control.checkpoint()
        self.names.append(name)
        if name == self.fail:
            raise OSError("injected service launch failure")

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        control.checkpoint()
        self.pins.append(name)
        return namespace(name)

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        control.checkpoint()
        self.closed_namespaces.append(name)
        return stopped(name)

    def require_running(self) -> None:
        assert not self.stopped

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        control.checkpoint()
        self.stopped = True
        return ()


def prepared(root: Path) -> tuple[AdminLocalServices, Commands, Services]:
    (root / "state").mkdir()
    commands, services = Commands(root), Services()
    site = AdminLocalServices(spec(root), commands, services)
    site.prepare(guard())
    return site, commands, services


def test_start_order_original_ports_and_no_legacy_environment(node_path: Path) -> None:
    site, commands, services = prepared(node_path)
    assert site.start(guard()) == "http://127.0.0.1:12001/admin"
    assert services.names == ["mysql", "redis", "search", "php", "nginx"]
    assert services.pins == ["nginx", "php"]
    config = [args for args in commands.calls if CONFIGURE in args][0]
    assert config[-4:] == ("12002", "12003", "12001", "12004")
    search = (node_path / "state/elasticsearch/config/elasticsearch.yml").read_text()
    assert "cluster.name: original" in search and search.count("http.port:") == 1
    assert "http.port: 12004" in search and "transport.port: 12005" in search
    nginx = (node_path / "state/nginx.conf").read_text()
    assert "127.0.0.1:12001" in nginx and "/state/run/php-fpm.sock" in nginx
    assert site.stop(guard()) == () and site.state == "stopped"
    assert site.stop(guard()) == ()
    for call in (site.prepare, site.start):
        with pytest.raises(RuntimeError):
            call(guard())
    assert services.names == ["mysql", "redis", "search", "php", "nginx"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("web", True),
        ("web", 0),
        ("web", 1023),
        ("web", 65536),
        ("web", "12000"),
        ("redis", 12001),
        ("transport", None),
    ],
)
def test_invalid_ports_rejected(field: str, value: Any) -> None:
    values: dict[str, Any] = dict(
        web=12001, database=12002, redis=12003, search=12004, transport=12005
    )
    values[field] = value
    with pytest.raises(ValueError):
        AdminPorts(**values)


@pytest.mark.parametrize("name", ["mysql", "redis", "search", "php", "nginx"])
def test_partial_start_keeps_original_group_for_cleanup(
    node_path: Path, name: str
) -> None:
    site, commands, services = prepared(node_path)
    services.fail = name
    with pytest.raises(OSError, match="injected"):
        site.start(guard())
    assert site.state == "failed"
    count = len(services.names)
    with pytest.raises(RuntimeError):
        site.start(guard())
    assert len(services.names) == count
    site.stop(guard())
    assert services.stopped


@pytest.mark.parametrize("reply", [b"", b"{}", b"ready\n", b"error"])
def test_bad_health_fails_without_configuration_or_frontend(
    node_path: Path, reply: bytes
) -> None:
    site, commands, services = prepared(node_path)
    commands.health = reply
    with pytest.raises(ValueError, match="health"):
        site.start(guard())
    assert services.names == ["mysql", "redis", "search"]
    assert not any(CONFIGURE in a for a in commands.calls)


def test_configuration_error_does_not_start_frontend(node_path: Path) -> None:
    site, commands, services = prepared(node_path)
    commands.config = b"other"
    with pytest.raises(ValueError, match="configuration"):
        site.start(guard())
    assert services.names == ["mysql", "redis", "search"]


def test_nonempty_seed_and_repeated_prepare_rejected(node_path: Path) -> None:
    (node_path / "state").mkdir()
    (node_path / "state/untouched").write_text("original")
    commands, services = Commands(node_path), Services()
    site = AdminLocalServices(spec(node_path), commands, services)
    with pytest.raises(ValueError):
        site.prepare(guard())
    assert (
        commands.calls == []
        and (node_path / "state/untouched").read_text() == "original"
    )
    with pytest.raises(RuntimeError):
        site.prepare(guard())


def test_fixed_service_commands_bind_only_declared_instance(node_path: Path) -> None:
    commands = service_commands(spec(node_path))
    assert commands["redis"][-4:] == ("--save", "", "--appendonly", "no")
    assert "--port=12002" in commands["mysql"]
    assert commands["search"][-1] == "elasticsearch"
    assert "--env" in commands["search"]
    assert all(
        args[0] == "/usr/bin/apptainer" and "--cleanenv" in args
        for args in commands.values()
    )


def test_config_preflight_failure_prevents_all_service_launches(
    node_path: Path,
) -> None:
    (node_path / "state").mkdir()
    first = RuntimeError("missing nginx include")

    class FailedPreflight(Commands):
        def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
            result = super().run(argv, control)
            if "nginx" in argv and "-t" in argv:
                raise first
            return result

    commands, services = FailedPreflight(node_path), Services()
    site = AdminLocalServices(spec(node_path), commands, services)
    with pytest.raises(RuntimeError) as caught:
        site.prepare(guard())
    assert caught.value is first and site.state == "failed" and services.names == []
    with pytest.raises(RuntimeError):
        site.start(guard())


def test_preflight_precedes_any_service_start(node_path: Path) -> None:
    site, commands, services = prepared(node_path)
    assert services.names == []
    assert any("nginx" in args and "-t" in args for args in commands.calls)
    assert any("php-fpm" in args and "-t" in args for args in commands.calls)
    assert "cp /etc/nginx/fastcgi_params /state/fastcgi_params" in SEED


def test_frontend_probe_receives_original_remaining_budget(node_path: Path) -> None:
    site, commands, _ = prepared(node_path)
    site.start(guard())
    health = [args for args in commands.calls if HEALTH in args]
    backend, frontend = health
    assert backend[-3:] == ("backend", "12003", "12004")
    assert frontend[-3:-1] == ("frontend", "12001")
    assert 0 < float(frontend[-1]) <= 5


def test_search_repository_is_fixed_private_and_ignores_old_config(
    node_path: Path,
) -> None:
    from lab_generate_skill.sites.shopping_admin.service_files import (
        write_service_files,
    )

    s = spec(node_path)
    target = node_path / "state/elasticsearch/config/elasticsearch.yml"
    target.parent.mkdir(parents=True)
    target.write_text("cluster.name: original\npath.repo: /untrusted/old\n")
    write_service_files(s, guard())
    result = target.read_text()
    assert (
        result.count("path.repo:") == 1
        and 'path.repo: ["/state/elasticsearch/snapshots"]' in result
    )
    assert "/untrusted/old" not in result
    assert (node_path / "state/elasticsearch/snapshots").is_dir()
    assert list((node_path / "state/elasticsearch/snapshots").iterdir()) == []
