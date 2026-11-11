"""Preparation boundary with explicit command doubles; no original Actor replay."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.media_initialization import initialize_media
from lab_generate_skill.sites.reddit.media_initialization_contract import (
    MediaInitialization,
)
from lab_generate_skill.sites.reddit.media_initialization_program import (
    INITIALIZE_MEDIA,
)
from lab_generate_skill.sites.reddit.service_programs import SEED
from reddit_services_fixtures import Commands, spec
from reddit_instance_fixtures import case
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def fresh(root: Path) -> Commands:
    (root / "state").mkdir(mode=0o700)
    (root / "state/media-native").mkdir(mode=0o700)
    return Commands(root)


def test_native_preparation_receipt_and_repeat_rejected(node_path: Path) -> None:
    commands = fresh(node_path)
    selected = spec(node_path)
    receipt = initialize_media(selected, commands, guard())
    assert receipt.service == selected
    assert receipt.before.directories == () and not receipt.before.files
    assert (
        receipt.after.directories == ("submission_images",) and not receipt.after.files
    )
    assert len(commands.calls) == 1 and INITIALIZE_MEDIA in commands.calls[0]
    receipt.check_baseline(receipt.after)
    with pytest.raises(ValueError):
        receipt.check_baseline(receipt.before)
    with pytest.raises(ValueError):
        initialize_media(selected, commands, guard())
    assert len(commands.calls) == 1
    assert MediaInitialization.model_validate_json(receipt.model_dump_json()) == receipt


@pytest.mark.parametrize(
    "entry", ["empty-directory", "file", "symlink", "foreign-directory", "mode"]
)
def test_nonfresh_media_rejected_before_constructor(
    node_path: Path, entry: str
) -> None:
    commands = fresh(node_path)
    root = node_path / "state/media-native"
    if entry == "file":
        (root / "unexpected").write_bytes(b"real bytes")
    elif entry == "symlink":
        (root / "submission_images").symlink_to(node_path, target_is_directory=True)
    elif entry == "mode":
        root.chmod(0o755)
    else:
        (
            root / ("submission_images" if entry == "empty-directory" else "foreign")
        ).mkdir()
    with pytest.raises(ValueError):
        initialize_media(spec(node_path), commands, guard())
    assert commands.calls == []


@pytest.mark.parametrize("failure", ["partial", "file", "foreign", "reply", "cancel"])
def test_partial_initialization_retained_and_instance_cannot_restart(
    node_path: Path, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, commands, groups, _ = case(node_path)
    original = commands.run

    def fail(argv: tuple[str, ...], control: OperationControl) -> bytes:
        result = original(argv, control)
        if INITIALIZE_MEDIA not in argv:
            return result
        root = Path(instance.files_plan.state_root) / "media-native"
        if failure == "partial":
            raise OSError("constructor completed directory before transport failed")
        if failure == "file":
            (root / "submission_images/foreign").write_bytes(b"full unexpected file")
        elif failure == "foreign":
            (root / "other").mkdir()
        elif failure == "reply":
            return b""
        elif failure == "cancel":
            raise OperationStopped("CANCELLED", "media-prepare")
        return result

    monkeypatch.setattr(commands, "run", fail)
    with pytest.raises((ValueError, OSError, OperationStopped)):
        instance.prepare(guard())
    assert (
        instance.state == "failed"
        and not groups
        and instance.media_initialization is None
    )
    assert (
        Path(instance.files_plan.state_root) / "media-native/submission_images"
    ).is_dir()
    calls = len(commands.calls)
    with pytest.raises(InvalidTransition):
        instance.prepare(guard())
    assert len(commands.calls) == calls


def test_cancel_before_effect_and_invalid_receipts(node_path: Path) -> None:
    commands = fresh(node_path)
    with pytest.raises(OperationStopped):
        initialize_media(spec(node_path), commands, guard(-1))
    assert commands.calls == []
    receipt = initialize_media(spec(node_path), commands, guard())
    invalid: tuple[dict[str, Any], ...] = (
        {"schema_version": "reddit-media-initialization/0"},
        {"constructor_sha256": "f" * 64},
        {"service": None},
        {"before": None},
        {"after": receipt.before},
        {"before": receipt.after},
        {
            "after": receipt.after.model_copy(
                update={"directories": ("submission_images", "other")}
            )
        },
    )
    for update in invalid:
        with pytest.raises(ValueError):
            MediaInitialization.model_validate(receipt.model_copy(update=update))


def test_restore_resume_never_reinitialize_media(node_path: Path) -> None:
    instance, commands, _, _ = case(node_path)
    instance.prepare(guard())
    receipt = instance.media_initialization
    assert receipt is not None
    instance.start(guard())
    saved = instance.snapshot_and_restart(guard())
    instance.restore(saved, guard())
    instance.resume(guard())
    instance.stop(guard())
    assert instance.media_initialization == receipt
    assert sum(INITIALIZE_MEDIA in c for c in commands.calls) == 1
    assert sum(SEED in c and "-ec" in c for c in commands.calls) == 1
