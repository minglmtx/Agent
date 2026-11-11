"""Original SIF constructor in tiny private state; no DB, HTTP or Actor."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.sites.reddit.media_initialization import initialize_media
from lab_generate_skill.sites.reddit.media_initialization_program import (
    INITIALIZE_MEDIA,
)
from lab_generate_skill.sites.reddit.service_commands import container
from lab_generate_skill.sites.reddit.service_programs import CONFIGURE
from reddit_native_program_fixture import OriginalImageCommands, prepare
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_fixture_uses_only_original_readonly_image_and_private_control_roots(
    node_path: Path,
) -> None:
    spec = prepare(node_path)
    commands = OriginalImageCommands(spec)
    argv = commands.command(
        container(spec, seeded=False) + ("/usr/local/bin/php", "-r", INITIALIZE_MEDIA)
    )
    mounts = [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == "--bind"]
    assert mounts == [
        str(node_path / "state") + ":/state",
        str(node_path / "control") + ":/control:ro",
        str(node_path / "runtime") + ":/runtime",
    ]
    assert argv[-1] == INITIALIZE_MEDIA and commands.calls == []
    assert not (node_path / "state/postgres").exists()


def test_original_php_factory_prepares_exact_empty_directory_and_rejects_repeat(
    node_path: Path,
) -> None:
    spec = prepare(node_path)
    commands = OriginalImageCommands(spec)
    base = container(spec, seeded=False)
    commands.run(
        base + ("/usr/local/bin/php", "-r", "if(false){" + INITIALIZE_MEDIA + "}"),
        guard(30),
    )
    assert (
        commands.run(
            base + ("/usr/local/bin/php", "-r", CONFIGURE, str(spec.ports.database)),
            guard(30),
        )
        == b"configured"
    )
    receipt = initialize_media(spec, commands, guard(30))
    assert receipt.before.directories == () and receipt.after.directories == (
        "submission_images",
    )
    assert not receipt.before.files and not receipt.after.files
    directory = node_path / "state/media-native/submission_images"
    assert directory.stat().st_mode & 0o777 == 0o755
    assert list(directory.iterdir()) == []
    before = len(commands.calls)
    with pytest.raises(ValueError):
        initialize_media(spec, commands, guard(30))
    assert len(commands.calls) == before
    assert not (node_path / "state/postgres").exists()
    assert not list((node_path / "runtime").iterdir())


def test_original_constructor_rejects_wrong_dsn_without_media_effect(
    node_path: Path,
) -> None:
    spec = prepare(node_path)
    commands = OriginalImageCommands(spec)
    with pytest.raises(CommandFailure):
        initialize_media(spec, commands, guard(30))
    assert list((node_path / "state/media-native").iterdir()) == []
    assert not (node_path / "state/postgres").exists()
