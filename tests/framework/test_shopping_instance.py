"""Same-instance lifecycle and all original partial handles, with fake effects."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.instance import ShoppingInstance
from shopping_services_fixtures import plan, Commands, Group
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


class Files:
    def stage(self, value: SiteFilesPlan, control: OperationControl) -> None:
        control.checkpoint()
        root = Path(value.node_root)
        root.mkdir(mode=0o700)
        for name in ("state", "logs", "image"):
            (root / name).mkdir()


class Lease:
    ports = (12001, 12002, 12003, 12004, 12005)

    def release(self, control: OperationControl) -> None:
        raise AssertionError("Inner lifecycle must never release original ports")


class Ports:
    def reserve(self, count: int, control: OperationControl) -> Lease:
        assert count == 5
        control.checkpoint()
        return Lease()


def instance(root: Path) -> tuple[ShoppingInstance, Commands, list[Group]]:
    root = root / "instance"
    commands = Commands(root)
    groups: list[Group] = []

    def factory(log_root: str, control: OperationControl) -> Group:
        assert Path(log_root).is_dir()
        control.checkpoint()
        group = Group(len(groups))
        groups.append(group)
        return group

    return (
        ShoppingInstance(
            plan(root),
            files=Files(),
            ports=Ports(),
            commands=commands,
            services=factory,
        ),
        commands,
        groups,
    )


def test_full_same_instance_snapshot_restore_resume(node_path: Path) -> None:
    site, commands, groups = instance(node_path)
    service = site.prepare(guard())
    endpoint = site.start(guard())
    (Path(service.runtime_root) / "php-error.log").write_text(
        "original runtime diagnostic"
    )
    snapshot = site.snapshot_and_restart(guard())
    assert len(groups) == 2 and groups[0].stopped and groups[0].quiesced
    assert (
        Path(service.files.log_root) / "generation-1/runtime/php-error.log"
    ).read_text() == "original runtime diagnostic"
    assert not list(Path(service.runtime_root).iterdir())
    assert site.restore(snapshot, guard()) == snapshot.inventory
    assert site.resume(guard()) == endpoint
    assert len(groups) == 3 and groups[1].stopped and not groups[2].stopped
    assert site.lease is not None and site.spec == service
    site.stop(guard())
    assert groups[2].stopped and Path(service.files.node_root).is_dir()
    for call in (site.prepare, site.start, site.snapshot_and_restart, site.resume):
        with pytest.raises(RuntimeError):
            call(guard())


@pytest.mark.parametrize(
    "phase",
    [
        "snapshot_unknown",
        "snapshot_copy",
        "restore_unknown",
        "restore_copy",
        "resume_start",
    ],
)
def test_failure_keeps_all_generations_and_denies_replay(
    node_path: Path, phase: str
) -> None:
    site, commands, groups = instance(node_path)
    site.prepare(guard())
    site.start(guard())
    if phase.startswith("snapshot"):
        if phase == "snapshot_unknown":
            groups[0].fail = "quiesce"
        else:
            commands.error = "cp"
        with pytest.raises((TimeoutError, OSError)):
            site.snapshot_and_restart(guard())
        assert len(groups) == 1
    else:
        snapshot = site.snapshot_and_restart(guard())
        if phase == "restore_unknown":
            groups[1].fail = "quiesce"
        elif phase == "restore_copy":
            commands.error = "cp"
        if phase != "resume_start":
            with pytest.raises((TimeoutError, OSError)):
                site.restore(snapshot, guard())
        else:
            site.restore(snapshot, guard())
            commands.error = "php"
            # Backend health is a fixed PHP command; retain the newly registered
            # generation and its three original masters on this failure.
            with pytest.raises(OSError):
                site.resume(guard())
    assert site.state == "failed"
    count = len(commands.calls)
    with pytest.raises(RuntimeError):
        site.snapshot_and_restart(guard())
    assert len(commands.calls) == count
    commands.error = None
    site.stop(guard())
    assert all(x.stopped for x in groups)
