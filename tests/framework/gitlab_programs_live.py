"""Cheap native Ruby/shell and tiny file fixtures; no GitLab service or database."""

import os
from pathlib import Path
import socket
import subprocess
import pytest
from lab_generate_skill.sites.gitlab.service_programs import (
    SEED,
    SERVICE_WRAPPER,
    CONFIGURE,
    POSTGRES_READY,
    BACKEND_READY,
    HTTP_READY,
)
from lab_generate_skill.sites.gitlab.snapshot_programs import (
    INVENTORY,
    CLEAR_SOCKETS,
    SOCKET_PATHS,
)
from lab_generate_skill.sites.gitlab.snapshot import GitlabInventory, StoppedSockets
from site_instance_fixtures import node_path as node_path

IMAGE = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/gitlab/947344df5a47a5a56785a0936330d08d097610bb27f38d40f278ac923f2f6d97/gitlab.sif"
)
RUBY = "/opt/gitlab/embedded/bin/ruby"


def native(root: Path, args: tuple[str, ...], *, success: bool = True) -> bytes:
    assert os.environ["SLURM_JOB_ID"] and IMAGE.stat().st_size == 22167199744
    argv = [
        "/usr/bin/apptainer",
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        "--bind",
        str(root / "state") + ":/state",
        "--bind",
        str(root / "snapshot") + ":/snapshot",
        "--bind",
        str(root / "control") + ":/control:ro",
        str(IMAGE),
        *args,
    ]
    completed = subprocess.run(argv, capture_output=True, timeout=30)
    if success:
        assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    else:
        assert completed.returncode != 0
    return completed.stdout


def tree(root: Path) -> Path:
    state = root / "state"
    state.mkdir()
    (root / "snapshot").mkdir()
    (root / "control").mkdir()
    (state / "data/nginx").mkdir(parents=True)
    (state / "data/nginx/logs").symlink_to("/var/log/gitlab/nginx")
    (state / "original").write_bytes(b"original bytes")
    return state


def test_all_injected_native_programs_compile_before_any_database(
    node_path: Path,
) -> None:
    state = node_path / "state"
    state.mkdir()
    (node_path / "snapshot").mkdir()
    control = node_path / "control"
    control.mkdir()
    (control / "noexec-check.sh").write_text("printf native_noexec_marker\n")
    assert (
        native(node_path, ("/bin/sh", "-n", "-c", "printf native_noexec_marker"))
        == b"native_noexec_marker"
    )
    assert native(node_path, ("/bin/sh", "-n", "/control/noexec-check.sh")) == b""
    for name, program in (("seed.sh", SEED), ("postgres-ready.sh", POSTGRES_READY)):
        (control / name).write_text(program)
        assert native(node_path, ("/bin/sh", "-n", "/control/" + name)) == b""
    (control / "service.sh").write_text(SERVICE_WRAPPER)
    assert native(node_path, ("/bin/bash", "-n", "/control/service.sh")) == b""
    (control / "malformed.sh").write_text("if\n")
    native(node_path, ("/bin/sh", "-n", "/control/malformed.sh"), success=False)
    for program in (CONFIGURE, BACKEND_READY, HTTP_READY, INVENTORY, CLEAR_SOCKETS):
        assert native(node_path, (RUBY, "-c", "-e", program)) == b"Syntax OK\n"
    assert not list(state.iterdir())


def test_native_tree_exact_copy_clear_restore_and_readonly_backup(
    node_path: Path,
) -> None:
    state = tree(node_path)
    original = GitlabInventory.model_validate_json(
        native(node_path, (RUBY, "-e", INVENTORY, "/state"))
    )
    assert (
        original.files == 1
        and original.symlinks == 1
        and original.bytes == len(b"original bytes")
    )
    native(node_path, ("/bin/cp", "-a", "--", "/state", "/snapshot/state"))
    backup = GitlabInventory.model_validate_json(
        native(node_path, (RUBY, "-e", INVENTORY, "/snapshot/state"))
    )
    assert backup == original
    (state / "original").write_bytes(b"changed")
    assert (
        GitlabInventory.model_validate_json(
            native(node_path, (RUBY, "-e", INVENTORY, "/state"))
        )
        != original
    )
    native(
        node_path, (RUBY, "-e", INVENTORY, "/snapshot/state", "clear"), success=False
    )
    assert (node_path / "snapshot/state/original").read_bytes() == b"original bytes"
    native(node_path, (RUBY, "-e", INVENTORY, "/state", "clear"))
    assert not list(state.iterdir())
    native(node_path, ("/bin/cp", "-a", "--", "/snapshot/state/.", "/state"))
    assert (
        GitlabInventory.model_validate_json(
            native(node_path, (RUBY, "-e", INVENTORY, "/state"))
        )
        == original
    )


@pytest.mark.parametrize(
    "kind", ["foreign_symlink", "wrong_log_link", "hardlink", "fifo", "socket"]
)
def test_unknown_alias_or_special_entry_refused_without_deletion(
    node_path: Path, kind: str
) -> None:
    state = tree(node_path)
    entry = state / "unexpected"
    if kind == "foreign_symlink":
        entry.symlink_to("/etc/passwd")
    elif kind == "wrong_log_link":
        entry = state / "data/nginx/logs"
        entry.unlink()
        entry.symlink_to("/etc")
    elif kind == "hardlink":
        os.link(state / "original", entry)
    elif kind == "fifo":
        os.mkfifo(entry)
    else:
        with socket.socket(socket.AF_UNIX) as endpoint:
            endpoint.bind(str(entry))
    native(node_path, (RUBY, "-e", INVENTORY, "/state", "clear"), success=False)
    assert entry.is_symlink() or entry.exists()
    assert (state / "original").read_bytes() == b"original bytes"


def sockets(state: Path) -> None:
    for relative in SOCKET_PATHS:
        path = state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with socket.socket(socket.AF_UNIX) as endpoint:
            endpoint.bind(str(path))
    (state / "data/postgresql/data").mkdir()


def test_only_original_stopped_sockets_accounted_and_removed(node_path: Path) -> None:
    state = tree(node_path)
    sockets(state)
    result = StoppedSockets.model_validate_json(
        native(node_path, (RUBY, "-e", CLEAR_SOCKETS))
    )
    assert result.removed == SOCKET_PATHS and result.absent == ()
    again = StoppedSockets.model_validate_json(
        native(node_path, (RUBY, "-e", CLEAR_SOCKETS))
    )
    assert again.removed == () and again.absent == SOCKET_PATHS
    assert (state / "original").read_bytes() == b"original bytes"


@pytest.mark.parametrize(
    "failure", ["regular_endpoint", "database_pid", "aliased_parent"]
)
def test_socket_cleanup_validates_all_before_unlink(
    node_path: Path, failure: str
) -> None:
    state = tree(node_path)
    sockets(state)
    if failure == "regular_endpoint":
        path = state / SOCKET_PATHS[-1]
        path.unlink()
        path.write_text("not a socket")
    elif failure == "database_pid":
        (state / "data/postgresql/data/postmaster.pid").write_text("original pid")
    else:
        source = state / "data/gitaly"
        target = node_path / "original-gitaly"
        source.rename(target)
        source.symlink_to(target)
    native(node_path, (RUBY, "-e", CLEAR_SOCKETS), success=False)
    assert (state / SOCKET_PATHS[0]).exists() and (state / SOCKET_PATHS[1]).exists()
    if failure == "aliased_parent":
        assert (node_path / "original-gitaly/gitaly.socket").exists()


def test_native_configuration_uses_original_shapes_and_exact_endpoints(
    node_path: Path,
) -> None:
    state = tree(node_path)
    pg = state / "data/postgresql/data"
    pg.mkdir(parents=True)
    (pg / "pg_ident.conf").write_text("original-map\n")
    (pg / "postmaster.pid").write_text("old seed pid\n")
    rails = state / "data/gitlab-rails/etc"
    rails.mkdir(parents=True)
    (rails / "gitlab.yml").write_text(
        "    host: original\n    port: 8023\n    email_enabled: true\n"
    )
    (rails / "puma.rb").write_text("workers 16\nbind 'tcp://127.0.0.1:8080'\n")
    gitaly = state / "data/gitaly"
    gitaly.mkdir()
    (gitaly / "config.toml").write_text("prometheus_listen_addr = 'localhost:9236'\n")
    assert (
        native(node_path, (RUBY, "-e", CONFIGURE, "12001", "12002", "native_user"))
        == b"configured"
    )
    assert (
        "    host: 127.0.0.1\n    port: 12001\n    email_enabled: false"
        in (rails / "gitlab.yml").read_text()
    )
    assert (rails / "puma.rb").read_text() == "workers 2\n\n"
    assert "127.0.0.1:12002" in (gitaly / "config.toml").read_text()
    assert (
        pg / "pg_ident.conf"
    ).read_text() == "gitlab native_user gitlab\ngitlab native_user gitlab-psql\noriginal-map\n"
    assert not (pg / "postmaster.pid").exists()
