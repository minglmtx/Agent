"""Coherent snapshot gate: exact copy/restore, corruption and once-only failure."""

from pathlib import Path
import pytest
from lab_generate_skill.sites.shopping.snapshot import ShoppingSnapshots
from lab_generate_skill.sites.shopping.services import SERVICE_NAMES
from shopping_services_fixtures import spec, Commands, Group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def original_group(generation: int = 0) -> Group:
    group = Group(generation)
    for name in SERVICE_NAMES:
        group.start(name, ("/fake",), guard())
        group.pin_namespace(name, guard())
    return group


def test_exact_original_snapshot_and_new_stopped_generation(node_path: Path) -> None:
    commands = Commands(node_path)
    store = ShoppingSnapshots(spec(node_path), commands)
    first = original_group().quiesce(guard())
    snapshot = store.save(first, guard())
    assert snapshot.original_stop == first and store.result == snapshot
    with pytest.raises(RuntimeError):
        store.save(first, guard())
    with pytest.raises(RuntimeError):
        store.restore(snapshot, first, guard())
    second = original_group(1).quiesce(guard())
    assert store.restore(snapshot, second, guard()) == snapshot.inventory
    assert store.restored == snapshot.inventory
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        store.restore(snapshot, second, guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "phase", ["changed_source", "changed_copy", "copy_failure", "existing_backup"]
)
def test_partial_save_never_returns_reusable_snapshot(
    node_path: Path, phase: str
) -> None:
    commands = Commands(node_path)
    store = ShoppingSnapshots(spec(node_path), commands)
    different = commands.inventory.model_copy(update={"sha256": "c" * 64})
    if phase == "changed_source":
        commands.scans = [commands.inventory, different]
    elif phase == "changed_copy":
        commands.scans = [commands.inventory, commands.inventory, different]
    elif phase == "copy_failure":
        commands.error = "cp"
    else:
        (node_path / "snapshot").mkdir()
    with pytest.raises((ValueError, OSError)):
        store.save(original_group().quiesce(guard()), guard())
    assert store.result is None
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        store.save(original_group().quiesce(guard()), guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "phase", ["corrupt_backup", "copy_failure", "restored_differs", "wrong_snapshot"]
)
def test_restore_verifies_before_mutation_and_retains_unknown(
    node_path: Path, phase: str
) -> None:
    commands = Commands(node_path)
    store = ShoppingSnapshots(spec(node_path), commands)
    snapshot = store.save(original_group().quiesce(guard()), guard())
    different = commands.inventory.model_copy(update={"sha256": "c" * 64})
    if phase == "corrupt_backup":
        commands.scans = [different]
    elif phase == "copy_failure":
        commands.error = "cp"
    elif phase == "restored_differs":
        commands.scans = [
            commands.inventory,
            commands.inventory,
            commands.inventory,
            different,
        ]
    else:
        snapshot = snapshot.model_copy(update={"inventory": different})
    count = len(commands.calls)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        store.restore(snapshot, original_group(1).quiesce(guard()), guard())
    assert store.restored is None
    calls = commands.calls[count:]
    if phase in ("corrupt_backup", "wrong_snapshot"):
        assert not any("clear" in x or "cp" in x for x in calls)
    else:
        count = len(commands.calls)
        with pytest.raises(RuntimeError):
            store.restore(snapshot, original_group(1).quiesce(guard()), guard())
        assert len(commands.calls) == count


def test_nonzero_database_exit_does_not_create_backup(node_path: Path) -> None:
    group = original_group()
    group.exitcode = 1
    store = ShoppingSnapshots(spec(node_path), Commands(node_path))
    with pytest.raises(ValueError):
        store.save(group.quiesce(guard()), guard())
    assert not (node_path / "snapshot").exists()
