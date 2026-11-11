"""Compile fixed scripts and verify real filesystem effects before Shopping DB."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.sites.shopping.service_programs import (
    SEED,
    CONFIGURE,
    HEALTH,
    MAIL_SINK,
)
from lab_generate_skill.sites.shopping.static_program import NATIVE_STATIC
from lab_generate_skill.sites.shopping.snapshot_program import INVENTORY
from lab_generate_skill.sites.shopping.snapshot import ShoppingInventory
from lab_generate_skill.sites.shopping.tasks.order_eta_programs import (
    RECORDED_ETA,
    PROTECTION,
)
from test_admin_database_native import IMAGE
from test_slurm_commands import guard
from shopping_native_diagnostics import retain_native_failure
from lab_generate_skill.sites.shopping.query_programs import (
    CORE_FINGERPRINT,
    LOCAL_MAIL,
)
from site_instance_fixtures import node_path as node_path


def base(root: Path) -> tuple[str, ...]:
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
        "--bind",
        str(root / "state") + ":/state",
        "--bind",
        str(root / "snapshot") + ":/snapshot",
        str(IMAGE),
    )


def test_exact_fixed_php_and_shell_programs_compile_without_database(
    tmp_path: Path,
) -> None:
    for name in ("state", "snapshot"):
        (tmp_path / name).mkdir()
    commands = CheckedNativeCommands(ProcessRunner())
    argv = base(tmp_path)
    commands.run(argv + ("sh", "-n", "-c", SEED), guard(10))
    for program in (
        CONFIGURE,
        HEALTH,
        MAIL_SINK,
        NATIVE_STATIC,
        INVENTORY,
        RECORDED_ETA,
        PROTECTION,
        CORE_FINGERPRINT,
        LOCAL_MAIL,
    ):
        commands.run(argv + ("php", "-r", "if(false){" + program + "}"), guard(10))


def test_exact_shopping_nginx_config_without_database(node_path: Path) -> None:
    from shopping_native_live import IMAGE as SHOPPING_IMAGE
    from lab_generate_skill.sites.shopping.service_files import write_controls
    from shopping_services_fixtures import spec

    tmp_path = node_path

    for name in (
        "state",
        "runtime",
        "control",
        "state/nginx",
        "state/nginx/client",
        "state/nginx/proxy",
        "state/nginx/fastcgi",
        "state/search",
        "state/search/config",
    ):
        (tmp_path / name).mkdir()
    (tmp_path / "state/search/config/elasticsearch.yml").write_text(
        "cluster.name: native\n"
    )
    argv = (
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
        str(tmp_path / "state") + ":/state",
        "--bind",
        str(tmp_path / "runtime") + ":/runtime",
        "--bind",
        str(tmp_path / "control") + ":/control:ro",
        str(SHOPPING_IMAGE),
    )
    commands = CheckedNativeCommands(ProcessRunner())
    try:
        original = commands.run(argv + ("cat", "/etc/nginx/fastcgi_params"), guard(15))
        (tmp_path / "state/fastcgi_params").write_bytes(original)
        write_controls(spec(tmp_path), guard(15))
        assert (tmp_path / "control/fastcgi_params").read_bytes() == original
        commands.run(
            argv
            + (
                "nginx",
                "-t",
                "-e",
                "/runtime/nginx-error.log",
                "-c",
                "/control/nginx.conf",
            ),
            guard(15),
        )
    except BaseException as error:
        output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "nginx-preflight"
        output.mkdir(mode=0o700)
        retain_native_failure(output, error)
        raise


def test_real_inventory_copy_clear_restore_and_tamper_detection(tmp_path: Path) -> None:
    state, snapshot = tmp_path / "state", tmp_path / "snapshot"
    state.mkdir(mode=0o700)
    snapshot.mkdir(mode=0o700)
    (state / ".hidden").write_bytes(b"private content\x00")
    # Reading legitimately updates atime. It must not look like a concurrent
    # writer; content/identity/mtime/ctime checks remain required.
    os.utime(state / ".hidden", (1, 1))
    (state / "nested").mkdir(mode=0o700)
    (state / "nested/file").write_text("original")
    (state / "nested").chmod(0o500)
    commands = CheckedNativeCommands(ProcessRunner())
    argv = base(tmp_path)

    def scan(path: str) -> ShoppingInventory:
        return ShoppingInventory.model_validate_json(
            commands.run(argv + ("php", "-r", INVENTORY, path), guard(10))
        )

    before = scan("/state")
    assert before.files == 2 and before.directories == 2 and before.bytes > 0
    commands.run(argv + ("cp", "-a", "--", "/state", "/snapshot/state"), guard(10))
    assert scan("/snapshot/state") == before
    (state / ".hidden").write_bytes(b"changed")
    assert scan("/state") != before
    commands.run(argv + ("php", "-r", INVENTORY, "/state", "clear"), guard(10))
    assert not list(state.iterdir())
    commands.run(argv + ("cp", "-a", "--", "/snapshot/state/.", "/state"), guard(10))
    assert scan("/state") == before
    with pytest.raises(CommandFailure):
        commands.run(
            argv + ("php", "-r", INVENTORY, "/snapshot/state", "clear"), guard(10)
        )
    assert scan("/snapshot/state") == before


@pytest.mark.parametrize("invalid", ["symlink", "hardlink", "fifo", "outside_root"])
def test_real_inventory_rejects_unsupported_entries_before_deletion(
    tmp_path: Path, invalid: str
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (tmp_path / "snapshot").mkdir()
    original = state / "original"
    original.write_text("must remain")
    if invalid == "symlink":
        (state / "link").symlink_to(original)
    elif invalid == "hardlink":
        (state / "link").hardlink_to(original)
    elif invalid == "fifo":
        import os

        os.mkfifo(state / "fifo")
    commands = CheckedNativeCommands(ProcessRunner())
    with pytest.raises(CommandFailure):
        commands.run(
            base(tmp_path)
            + (
                "php",
                "-r",
                INVENTORY,
                "/tmp" if invalid == "outside_root" else "/state",
                "clear",
            ),
            guard(10),
        )
    assert original.read_text() == "must remain"
