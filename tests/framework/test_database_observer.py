"""Authorized private initialization: strict input, once-only file, fail closed."""

import base64
import json
from pathlib import Path
import subprocess
from typing import Any
import pytest
from site_instance_fixtures import node_path as node_path
from test_admin_search_http import command
from test_admin_database_native import IMAGE
from test_admin_services import Commands, Services, spec, prepared
from test_slurm_commands import guard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.database_observer_program import (
    DATABASE_OBSERVER_INIT_PHP,
)
from lab_generate_skill.sites.shopping_admin.drain_program import DATABASE_DRAIN_PHP
from lab_generate_skill.sites.shopping_admin.services import AdminLocalServices


def config(root: Path, user: Any = "magentouser") -> Path:
    target = root / "app/app/etc/env.php"
    target.parent.mkdir(parents=True)
    data = {
        "db": {
            "connection": {
                "default": {"username": user, "password": "never-in-init-file"}
            }
        }
    }
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    target.write_text(
        "<?php return json_decode(base64_decode('" + encoded + "'),true);"
    )
    return target


def native(root: Path, prefix: str = "") -> subprocess.CompletedProcess[bytes]:
    argv = list(command(prefix + DATABASE_OBSERVER_INIT_PHP))
    argv[argv.index(str(IMAGE)) : argv.index(str(IMAGE))] = [
        "--bind",
        str(root) + ":/state",
    ]
    return subprocess.run(argv, capture_output=True, timeout=15)


def test_original_account_only_private_file_and_repeat_rejected(
    node_path: Path,
) -> None:
    original = config(node_path)
    before = original.read_bytes()
    result = native(node_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"observer-configured"
    target = node_path / "database-observer-init.sql"
    data = target.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    assert b"GRANT PROCESS ON *.* TO " in data and b"WHERE User = 'magentouser'" in data
    assert b"CREATE USER" not in data and b"never-in-init-file" not in data
    assert len(data.splitlines()) == 5 and original.read_bytes() == before
    repeated = native(node_path)
    assert repeated.returncode == 2 and target.read_bytes() == data


@pytest.mark.parametrize(
    "user",
    [
        None,
        True,
        {},
        "",
        "x" * 33,
        "a'b",
        "a\nb",
        "root",
        "ROOT",
        "a;DROP",
        " a",
        "a@host",
        "\0",
    ],
)
def test_invalid_account_has_no_file_effect(node_path: Path, user: Any) -> None:
    config(node_path, user)
    result = native(node_path)
    assert (
        result.returncode == 2 and b"Unsupported private application" in result.stderr
    )
    assert not (node_path / "database-observer-init.sql").exists()


@pytest.mark.parametrize(
    "fault", ["missing", "link", "directory_link", "existing_directory"]
)
def test_invalid_paths_or_existing_target_preserved(
    node_path: Path, fault: str
) -> None:
    original = config(node_path)
    if fault == "missing":
        original.unlink()
    elif fault == "link":
        original.rename(original.with_name("kept.php"))
        original.symlink_to("kept.php")
    elif fault == "directory_link":
        parent = original.parent
        parent.rename(parent.with_name("kept"))
        parent.symlink_to("kept", target_is_directory=True)
    else:
        (node_path / "database-observer-init.sql").mkdir()
    result = native(node_path)
    assert result.returncode == 2
    assert not (node_path / "database-observer-init.sql").is_file()


@pytest.mark.parametrize("fault", ["write", "flush", "close", "write_close"])
def test_write_and_cleanup_failure_preserve_primary(
    node_path: Path, fault: str
) -> None:
    config(node_path)
    prefix = "namespace ObserverFault;use \\RuntimeException;use \\Throwable;"
    if "write" in fault:
        prefix += "function fwrite($f,$s){return $f===STDERR?\\fwrite($f,$s):0;}"
    if fault == "flush":
        prefix += "function fflush($f){return false;}"
    if "close" in fault:
        prefix += "function fclose($f){\\fclose($f);return false;}"
    result = native(node_path, prefix)
    assert result.returncode == 2
    error = json.loads(result.stderr.splitlines()[-1])
    assert (error["primary"] is not None) == (fault != "close")
    assert (error["cleanup"] is not None) == ("close" in fault)
    assert (node_path / "database-observer-init.sql").exists()


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"null",
        b"{}",
        b'{"other_sql_connections":false,"sql_transactions":0}',
        b'{"other_sql_connections":1,"sql_transactions":0}',
        b'{"other_sql_connections":0,"sql_transactions":0,"extra":0}',
    ],
)
def test_initial_observation_rejection_prevents_frontends(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, bad: bytes
) -> None:
    site, commands, services = prepared(node_path)
    original = commands.run

    def run(argv: tuple[str, ...], control: OperationControl) -> bytes:
        return bad if DATABASE_DRAIN_PHP in argv else original(argv, control)

    monkeypatch.setattr(commands, "run", run)
    with pytest.raises(ValueError):
        site.start(guard())
    assert services.names == ["mysql", "redis", "search"] and site.state == "failed"
    with pytest.raises(RuntimeError):
        site.start(guard())
    site.stop(guard())
    assert services.stopped


def test_outside_authorized_tmp_scope_has_no_command_effect(tmp_path: Path) -> None:
    commands, services = Commands(tmp_path), Services()
    outside = spec(tmp_path).model_copy(
        update={
            "layout": spec(tmp_path).layout.model_copy(
                update={
                    "node_root": "/var/private",
                    "state_root": "/var/private/state",
                    "image_path": "/var/private/image.sif",
                }
            )
        }
    )
    site = AdminLocalServices(outside, commands, services)
    with pytest.raises(ValueError, match="private /tmp"):
        site.prepare(guard())
    assert not commands.calls and not services.names
