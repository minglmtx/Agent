"""Exact original snapshot/new-generation restore and no retry on partial copy."""

import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.sites.reddit.snapshot import (
    RedditSnapshots,
    RedditSnapshot,
    RedditInventory,
)
from lab_generate_skill.sites.reddit.service_commands import container
from reddit_services_fixtures import spec
from reddit_snapshot_fixtures import TreeCommands, stopped
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_original_snapshot_and_full_restore_preserve_all_state(node_path: Path) -> None:
    selected = spec(node_path)
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(selected, commands)
    first, pins = stopped()
    saved = snapshots.save(first, pins, guard())
    assert saved.service == selected and saved.original_stop == first
    assert RedditSnapshot.model_validate_json(saved.model_dump_json()) == saved
    assert snapshots.result == saved
    second, newpins = stopped(1)
    commands.scans = [
        saved.inventory,
        saved.inventory.model_copy(update={"sha256": "b" * 64}),
        saved.inventory,
    ]
    assert snapshots.restore(saved, second, newpins, guard()) == saved.inventory
    assert snapshots.restored == saved.inventory
    clear = next(c for c in commands.calls if "clear" in c)
    assert selected.snapshot_root + ":/snapshot:ro" in clear
    assert selected.snapshot_root + ":/snapshot" in container(
        selected, seeded=False, snapshot="save"
    )
    with pytest.raises(InvalidTransition):
        snapshots.save(first, pins, guard())
    with pytest.raises(InvalidTransition):
        snapshots.restore(saved, second, newpins, guard())


@pytest.mark.parametrize(
    "which", ["source-changed", "snapshot-changed", "copy-unknown"]
)
def test_save_failure_retains_original_attempt_and_never_adopts_partial(
    node_path: Path, which: str
) -> None:
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(spec(node_path), commands)
    altered = commands.inventory.model_copy(update={"sha256": "b" * 64})
    if which == "source-changed":
        commands.scans = [commands.inventory, altered]
    elif which == "snapshot-changed":
        commands.scans = [commands.inventory, commands.inventory, altered]
    else:
        commands.error = "/bin/cp"
    facts, pins = stopped()
    with pytest.raises((ValueError, OSError)):
        snapshots.save(facts, pins, guard())
    assert snapshots.saving and snapshots.result is None
    with pytest.raises(InvalidTransition):
        snapshots.save(facts, pins, guard())


@pytest.mark.parametrize(
    "which",
    [
        "snapshot-corrupt",
        "target-invalid",
        "restored-different",
        "clear-unknown",
        "copy-unknown",
    ],
)
def test_restore_failure_is_not_hidden_or_automatically_repeated(
    node_path: Path, which: str
) -> None:
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(spec(node_path), commands)
    facts, pins = stopped()
    saved = snapshots.save(facts, pins, guard())
    second, newpins = stopped(1)
    altered = saved.inventory.model_copy(update={"sha256": "c" * 64})
    if which == "snapshot-corrupt":
        commands.scans = [altered]
    elif which == "target-invalid":
        commands.error = "/state"
    elif which == "restored-different":
        commands.scans = [saved.inventory, saved.inventory, altered]
    elif which == "clear-unknown":
        commands.error = "clear"
    else:
        commands.error = "/bin/cp"
    before = len(commands.calls)
    with pytest.raises((ValueError, OSError)):
        snapshots.restore(saved, second, newpins, guard())
    assert snapshots.restored is None
    calls = commands.calls[before:]
    if which in ("snapshot-corrupt", "target-invalid"):
        assert not any("clear" in c or "/bin/cp" in c for c in calls)
    else:
        assert snapshots.restoring
        with pytest.raises(InvalidTransition):
            snapshots.restore(saved, second, newpins, guard())


@pytest.mark.parametrize(
    "which",
    [
        "foreign-snapshot",
        "old-generation",
        "foreign-pins",
        "no-snapshot",
        "foreign-thread",
    ],
)
def test_restore_requires_original_snapshot_new_stopped_generation_and_owner(
    node_path: Path, which: str
) -> None:
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(spec(node_path), commands)
    first, pins = stopped()
    saved = snapshots.save(first, pins, guard())
    second, newpins = stopped(1)
    if which == "foreign-snapshot":
        saved = saved.model_copy(
            update={
                "inventory": saved.inventory.model_copy(update={"sha256": "d" * 64})
            }
        )
    elif which == "old-generation":
        second, newpins = first, pins
    elif which == "foreign-pins":
        newpins = pins
    elif which == "no-snapshot":
        snapshots.result = None
    else:
        snapshots.owner = (os.getpid() + 1, snapshots.owner[1])
    before = len(commands.calls)
    with pytest.raises((ValueError, InvalidTransition, OwnershipConflict)):
        snapshots.restore(saved, second, newpins, guard())
    assert len(commands.calls) == before and not snapshots.restoring


@pytest.mark.parametrize("code", [1, 143, -15])
def test_abnormal_stop_prevents_snapshot_before_any_io(
    node_path: Path, code: int
) -> None:
    from reddit_services_fixtures import Group

    group = Group()
    for name in ["postgres", "php", "nginx"]:
        group.start(name, ("/explicit-fake",), guard())
        group.pin_namespace(name, guard())
    group.exitcode = code
    facts = group.quiesce(guard())
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(spec(node_path), commands)
    with pytest.raises(ValueError):
        snapshots.save(facts, tuple(group.pins), guard())
    assert (
        not snapshots.saving
        and commands.calls == []
        and not Path(snapshots.spec.snapshot_root).exists()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("files", True),
        ("files", -1),
        ("directories", 0),
        ("bytes", None),
        ("bytes", -1),
        ("bytes", 2**63),
        ("sha256", ""),
        ("sha256", "x" * 64),
    ],
)
def test_inventory_illegal_or_extreme_counts_refused(field: str, value: Any) -> None:
    data: dict[str, Any] = {
        "sha256": "a" * 64,
        "files": 0,
        "directories": 1,
        "bytes": 0,
    }
    data[field] = value
    with pytest.raises(ValueError):
        RedditInventory.model_validate(data)


def test_empty_tree_and_cancellation_before_save_have_no_copy(node_path: Path) -> None:
    assert RedditInventory(sha256="a" * 64, files=0, directories=1, bytes=0).bytes == 0
    commands = TreeCommands(node_path)
    snapshots = RedditSnapshots(spec(node_path), commands)
    facts, pins = stopped()

    class Cancelled:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        snapshots.save(facts, pins, Cancelled())
    assert not snapshots.saving and commands.calls == []
