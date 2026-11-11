"""Whole instance fake effects, using the actual Reddit orchestration modules."""

from pathlib import Path
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.instance import RedditInstance
from lab_generate_skill.sites.reddit.progress import RedditPhase
from reddit_services_fixtures import spec, Group
from reddit_snapshot_fixtures import TreeCommands


class Files:
    def __init__(self) -> None:
        self.calls = 0

    def stage(self, plan: SiteFilesPlan, control: OperationControl) -> None:
        control.checkpoint()
        self.calls += 1
        root = Path(plan.node_root)
        root.mkdir(mode=0o700)
        for name in ["state", "image", "logs"]:
            (root / name).mkdir(mode=0o700)


class Lease:
    ports = (12001, 12002)

    def release(self, control: OperationControl) -> None:
        raise AssertionError("Only outer original resource can release ports")


class Ports:
    def reserve(self, count: int, control: OperationControl) -> Lease:
        control.checkpoint()
        assert count == 2
        return Lease()


class OwnedGroup(Group):
    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        if self.fail == "stop":
            raise OSError("original group cleanup failed")
        return super().stop(control)


def case(
    parent: Path,
) -> tuple[RedditInstance, TreeCommands, list[OwnedGroup], list[RedditPhase]]:
    root = parent / "instance"
    commands = TreeCommands(root)
    groups: list[OwnedGroup] = []
    phases: list[RedditPhase] = []

    def services(log_root: str, control: OperationControl) -> OwnedGroup:
        control.checkpoint()
        assert Path(log_root).is_dir()
        group = OwnedGroup(len(groups))
        groups.append(group)
        return group

    return (
        RedditInstance(
            spec(root).files,
            files=Files(),
            ports=Ports(),
            commands=commands,
            services=services,
            progress=phases.append,
        ),
        commands,
        groups,
        phases,
    )
