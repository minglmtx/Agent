"""Original instance generations and full lifecycle with fake native effects."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.instance import GitlabInstance
from lab_generate_skill.sites.gitlab.progress import GitlabPhase
from lab_generate_skill.sites.gitlab.service_programs import HTTP_READY
from gitlab_native_fixtures import plan, Commands, Group, Files, Ports
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def instance(
    root: Path,
    *,
    native_shutdown: bool = False,
) -> tuple[GitlabInstance, Commands, list[Group], list[GitlabPhase]]:
    root = root / "instance"
    commands = Commands(root)
    groups: list[Group] = []
    phases: list[GitlabPhase] = []

    def factory(log_root: str, control: OperationControl) -> Group:
        assert Path(log_root).is_dir()
        control.checkpoint()
        if native_shutdown:
            from gitlab_shutdown_fixtures import ShutdownGroup

            group: Group = ShutdownGroup(len(groups), Path(log_root))
        else:
            group = Group(len(groups))
        groups.append(group)
        return group

    files_plan = plan(root)
    if native_shutdown:
        from lab_generate_skill.sites.gitlab.image import GITLAB_IMAGE_SHA

        files_plan = files_plan.model_copy(
            update={
                "image": files_plan.image.model_copy(
                    update={"sha256": GITLAB_IMAGE_SHA}
                )
            }
        )
    return (
        GitlabInstance(
            files_plan,
            database_peer_user="native_user",
            files=Files(),
            ports=Ports(),
            commands=commands,
            services=factory,
            progress=phases.append,
        ),
        commands,
        groups,
        phases,
    )


def test_prepare_snapshot_full_restore_original_new_generation_confirmed(
    node_path: Path,
) -> None:
    site, commands, groups, phases = instance(node_path)
    service = site.prepare(guard())
    endpoint = site.start(guard())
    assert phases[:8] == list(GitlabPhase)
    snapshot = site.snapshot_and_restart(guard())
    assert len(groups) == 2 and groups[0].quiesced and groups[0].stopped
    assert site.restore(snapshot, guard()) == snapshot.inventory
    assert len(groups) == 3 and groups[1].quiesced and groups[1].stopped
    assert site.resume(guard()) == endpoint and len(groups) == 3
    assert site.lease is not None and site.spec == service
    site.stop(guard())
    assert all(g.stopped for g in groups) and Path(service.files.node_root).exists()
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
        "restore_start",
        "resume_health",
    ],
)
def test_partial_failure_retains_all_original_groups_and_never_restarts(
    node_path: Path, phase: str
) -> None:
    site, commands, groups, phases = instance(node_path)
    site.prepare(guard())
    site.start(guard())
    if phase.startswith("snapshot"):
        if phase == "snapshot_unknown":
            groups[0].fail = "quiesce"
        else:
            commands.error = "/bin/cp"
        with pytest.raises((OSError, TimeoutError)):
            site.snapshot_and_restart(guard())
        assert len(groups) == 1
    else:
        snapshot = site.snapshot_and_restart(guard())
        if phase == "restore_unknown":
            groups[1].fail = "quiesce"
        elif phase == "restore_copy":
            commands.error = "/bin/cp"
        elif phase == "restore_start":
            commands.error = HTTP_READY
        if phase == "resume_health":
            site.restore(snapshot, guard())
            commands.error = HTTP_READY
            with pytest.raises(OSError):
                site.resume(guard())
        else:
            with pytest.raises((OSError, TimeoutError)):
                site.restore(snapshot, guard())
    assert site.state == "failed"
    count = len(commands.calls)
    for call in (site.start, site.snapshot_and_restart, site.resume):
        with pytest.raises(RuntimeError):
            call(guard())
    assert len(commands.calls) == count
    commands.error = None
    site.stop(guard())
    assert all(g.stopped for g in groups)


def test_expiry_before_prepare_and_foreign_thread_do_not_stage(node_path: Path) -> None:
    site, commands, groups, phases = instance(node_path)
    with pytest.raises(OperationStopped):
        site.prepare(guard(-1))
    assert (
        not commands.calls
        and not (node_path / "instance").exists()
        and site.state == "new"
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(RuntimeError):
            executor.submit(site.prepare, guard()).result()
    assert not commands.calls and not (node_path / "instance").exists()


def test_invalid_peer_user_rejected_before_any_stage(node_path: Path) -> None:
    with pytest.raises(ValueError):
        GitlabInstance(
            plan(node_path / "instance"),
            database_peer_user="invalid\npeer",
            files=Files(),
            ports=Ports(),
            commands=Commands(node_path),
            services=lambda root, control: Group(),
        )
    assert not (node_path / "instance").exists()
