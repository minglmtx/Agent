"""Full-tree integrity, exact original pins and once-only destructive phases."""

from pathlib import Path
import pytest
from lab_generate_skill.sites.gitlab.service_commands import SERVICE_NAMES
from lab_generate_skill.sites.gitlab.snapshot import GitlabSnapshots, StoppedSockets
from lab_generate_skill.sites.gitlab.snapshot_programs import (
    CLEAR_SOCKETS,
    SOCKET_PATHS,
)
from gitlab_native_fixtures import spec, Commands, Group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def original_group(generation: int = 0) -> Group:
    group = Group(generation)
    for name in SERVICE_NAMES:
        group.start(name, ("/fake",), guard())
        group.pin_namespace(name, guard())
    return group


def test_original_snapshot_and_new_generation_restore_once(node_path: Path) -> None:
    commands = Commands(node_path)
    store = GitlabSnapshots(spec(node_path), commands)
    first = original_group()
    stopped = first.quiesce(guard())
    snapshot = store.save(stopped, tuple(first.pins), guard())
    assert (
        snapshot.original_stop == stopped and snapshot.inventory == commands.inventory
    )
    with pytest.raises(RuntimeError):
        store.save(stopped, tuple(first.pins), guard())
    with pytest.raises(RuntimeError):
        store.restore(snapshot, stopped, tuple(first.pins), guard())
    second = original_group(1)
    newstop = second.quiesce(guard())
    assert (
        store.restore(snapshot, newstop, tuple(second.pins), guard())
        == snapshot.inventory
    )
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        store.restore(snapshot, newstop, tuple(second.pins), guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "phase",
    [
        "changed_source",
        "changed_copy",
        "copy_failure",
        "existing_backup",
        "socket_failure",
    ],
)
def test_partial_snapshot_retains_original_and_denies_replay(
    node_path: Path, phase: str
) -> None:
    commands = Commands(node_path)
    store = GitlabSnapshots(spec(node_path), commands)
    different = commands.inventory.model_copy(update={"sha256": "c" * 64})
    if phase == "changed_source":
        commands.scans = [commands.inventory, different]
    elif phase == "changed_copy":
        commands.scans = [commands.inventory, commands.inventory, different]
    elif phase == "copy_failure":
        commands.error = "/bin/cp"
    elif phase == "socket_failure":
        commands.error = CLEAR_SOCKETS
    else:
        (node_path / "snapshot").mkdir()
    group = original_group()
    stopped = group.quiesce(guard())
    with pytest.raises((ValueError, OSError)):
        store.save(stopped, tuple(group.pins), guard())
    assert store.result is None
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        store.save(stopped, tuple(group.pins), guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "phase",
    [
        "corrupt_backup",
        "copy_failure",
        "restored_differs",
        "socket_failure",
        "wrong_snapshot",
    ],
)
def test_restore_preflight_partial_failure_and_no_replay(
    node_path: Path, phase: str
) -> None:
    commands = Commands(node_path)
    store = GitlabSnapshots(spec(node_path), commands)
    first = original_group()
    snapshot = store.save(first.quiesce(guard()), tuple(first.pins), guard())
    different = commands.inventory.model_copy(update={"sha256": "c" * 64})
    if phase == "corrupt_backup":
        commands.scans = [different]
    elif phase == "copy_failure":
        commands.error = "/bin/cp"
    elif phase == "restored_differs":
        commands.scans = [commands.inventory, commands.inventory, different]
    elif phase == "socket_failure":
        commands.error = CLEAR_SOCKETS
    else:
        snapshot = snapshot.model_copy(update={"inventory": different})
    second = original_group(1)
    stopped = second.quiesce(guard())
    count = len(commands.calls)
    with pytest.raises((ValueError, OSError, RuntimeError)):
        store.restore(snapshot, stopped, tuple(second.pins), guard())
    assert store.restored is None
    if phase in ("corrupt_backup", "wrong_snapshot"):
        assert not any(
            "clear" in x or "/bin/cp" in x or CLEAR_SOCKETS in x
            for x in commands.calls[count:]
        )
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        store.restore(snapshot, stopped, tuple(second.pins), guard())
    assert len(commands.calls) == count


def test_foreign_original_pins_and_missing_socket_accounting_denied(
    node_path: Path,
) -> None:
    commands = Commands(node_path)
    store = GitlabSnapshots(spec(node_path), commands)
    first = original_group()
    stopped = first.quiesce(guard())
    second = original_group(1)
    with pytest.raises(ValueError):
        store.save(stopped, tuple(second.pins), guard())
    assert not commands.calls and not (node_path / "snapshot").exists()
    with pytest.raises(ValueError):
        StoppedSockets(removed=SOCKET_PATHS[:1], absent=SOCKET_PATHS)
