"""Compile original PHP/FPM/nginx controls without seeding or starting a DB."""

from pathlib import Path
import pytest
from lab_generate_skill.sites.reddit.service_commands import container
from lab_generate_skill.sites.reddit.service_programs import CONFIGURE
from lab_generate_skill.sites.reddit.service_files import write_controls
from lab_generate_skill.sites.reddit.services import preflight
from lab_generate_skill.adapters.processes.capture import CommandFailure
from reddit_native_program_fixture import ENV, IMAGE, OriginalImageCommands, prepare
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_new_control_fixture_binds_only_owned_state_and_exact_readonly_image(
    node_path: Path,
) -> None:
    selected = prepare(node_path)
    adapter = OriginalImageCommands(selected)
    command = adapter.command(
        container(selected, seeded=False) + ("/usr/local/bin/php", "-v")
    )
    assert str(IMAGE) in command and selected.files.image_path not in command
    mounts = [command[i + 1] for i, x in enumerate(command[:-1]) if x == "--bind"]
    assert mounts == [
        str(node_path / "state") + ":/state",
        str(node_path / "control") + ":/control:ro",
        str(node_path / "runtime") + ":/runtime",
    ]
    assert "bind-paths,hostfs,cwd" in command
    with pytest.raises(ValueError):
        adapter.command(("/usr/bin/apptainer", "exec", "/outside/image.sif"))
    assert adapter.calls == [] and not (node_path / "state/postgres").exists()


def test_original_image_compiles_and_transforms_only_private_controls(
    node_path: Path,
) -> None:
    selected = prepare(node_path)
    adapter = OriginalImageCommands(selected)
    assert IMAGE.stat().st_size == selected.files.image.size_bytes
    preflight(selected, adapter, guard(60))
    # Verify only binary presence, never run postgres or seed data in this check.
    adapter.run(
        container(selected, seeded=False)
        + (
            "/bin/sh",
            "-c",
            "test -x /usr/bin/pg_isready && test -x /usr/bin/postgres && test -x /usr/bin/psql",
        ),
        guard(20),
    )
    raw = adapter.run(
        container(selected, seeded=False)
        + ("/usr/local/bin/php", "-r", CONFIGURE, str(selected.ports.database)),
        guard(20),
    )
    assert raw == b"configured"
    env = (node_path / "state/app.env").read_text()
    assert (
        'DATABASE_URL="postgresql://postmill@localhost/postmill?host=/runtime&port=12002"'
        in env
    )
    assert 'UPLOAD_DSN="file:///state/media-native"' in env and 'UPLOAD_ROOT="/"' in env
    assert (
        "ENABLE_EXPERIMENTAL_REST_API=1" in env
        and 'APP_SECRET="engineering-only-not-a-real-secret"' in env
    )
    write_controls(selected, guard(5))
    for tail in [
        ("/usr/local/sbin/php-fpm", "--test", "--fpm-config", "/control/php.conf"),
        (
            "/usr/sbin/nginx",
            "-t",
            "-e",
            "/runtime/nginx-error.log",
            "-c",
            "/control/nginx.conf",
        ),
    ]:
        adapter.run(container(selected, seeded=False) + tail, guard(20))
    assert not (node_path / "state/postgres").exists()


@pytest.mark.parametrize("kind", ["duplicate-key", "missing-key", "invalid-port"])
def test_original_native_config_rejects_before_writing(
    node_path: Path, kind: str
) -> None:
    selected = prepare(node_path)
    adapter = OriginalImageCommands(selected)
    text = ENV
    if kind == "duplicate-key":
        text += 'UPLOAD_DSN="duplicate"\n'
    elif kind == "missing-key":
        text = text.replace('UPLOAD_ROOT="/old"\n', "")
    path = node_path / "state/app.env"
    path.write_text(text)
    port = "0" if kind == "invalid-port" else str(selected.ports.database)
    with pytest.raises(CommandFailure):
        adapter.run(
            container(selected, seeded=False)
            + ("/usr/local/bin/php", "-r", CONFIGURE, port),
            guard(20),
        )
    assert path.read_text() == text and not (node_path / "state/postgres").exists()
