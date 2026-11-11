"""Same-version native3/tree/instance composition with explicit fake effects."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.sites.reddit.instance import RedditInstance
from lab_generate_skill.sites.reddit.progress import RedditPhase
from lab_generate_skill.sites.reddit.service_programs import SEED, TRUST_ACCOUNT
from reddit_instance_fixtures import case, Files, Ports
from reddit_services_fixtures import spec
from reddit_snapshot_fixtures import TreeCommands
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_full_native3_snapshot_restore_resume_and_original_handles(
    node_path: Path,
) -> None:
    instance, commands, groups, phases = case(node_path)
    selected = instance.prepare(guard())
    endpoint = instance.start(guard())
    assert endpoint == selected.endpoint and len(groups) == 1
    (Path(selected.runtime_root) / "nginx-access.log").write_text("original diagnostic")
    saved = instance.snapshot_and_restart(guard())
    assert (
        len(groups) == 2
        and groups[0].quiesced
        and groups[0].stopped
        and not groups[1].stopped
    )
    assert (
        Path(selected.files.log_root) / "generation-1/runtime/nginx-access.log"
    ).read_text() == "original diagnostic"
    assert instance.restore(saved, guard()) == saved.inventory
    assert instance.state == "restored" and groups[1].quiesced and groups[1].stopped
    assert instance.resume(guard()) == endpoint and len(groups) == 3
    assert sum(TRUST_ACCOUNT in c for c in commands.calls) == 1
    assert (
        all(g.pins for g in groups)
        and len({p.init.process_id for g in groups for p in g.pins}) == 9
    )
    assert (
        phases[0] == RedditPhase.IMAGE_BEGIN and phases[-1] == RedditPhase.RESUME_READY
    )
    assert (
        phases.count(RedditPhase.BACKEND_READY) == 3
        and phases.count(RedditPhase.FRONTEND_READY) == 3
    )
    instance.stop(guard())
    instance.stop(guard())
    assert all(g.stopped for g in groups) and instance.state == "stopped"
    assert Path(selected.files.node_root).is_dir()  # no leaf release/removal
    with pytest.raises(InvalidTransition):
        instance.prepare(guard())
    with pytest.raises(InvalidTransition):
        instance.resume(guard())


@pytest.mark.parametrize(
    "failure",
    [
        "seed",
        "start",
        "stop-unknown",
        "stop-abnormal",
        "snapshot-copy",
        "restore-copy",
        "runtime-special",
        "resume",
    ],
)
def test_partial_failure_does_not_create_another_generation_or_repeat_original_operation(
    node_path: Path, failure: str
) -> None:
    instance, commands, groups, _ = case(node_path)
    if failure == "seed":
        commands.error = SEED
    with pytest.raises((OSError, TimeoutError, ValueError)):
        instance.prepare(guard())
        if failure == "start":
            commands.trusted = b"bad"
        instance.start(guard())
        if failure == "stop-unknown":
            groups[-1].fail = "quiesce"
        elif failure == "stop-abnormal":
            groups[-1].exitcode = 1
        elif failure == "snapshot-copy":
            commands.error = "/bin/cp"
        elif failure == "runtime-special":
            (Path(instance.files_plan.node_root) / "runtime/foreign").mkdir()
        saved = instance.snapshot_and_restart(guard())
        if failure == "restore-copy":
            commands.error = "/bin/cp"
        instance.restore(saved, guard())
        if failure == "resume":
            commands.health = b"bad"
        instance.resume(guard())
    assert instance.state == "failed"
    expected = (
        0
        if failure == "seed"
        else 3 if failure == "resume" else 2 if failure == "restore-copy" else 1
    )
    assert len(groups) == expected
    if failure == "stop-abnormal":
        proof = instance.generations[-1].quiescence
        assert proof is not None and all(m.returncode == 1 for m in proof.masters)
        assert instance.snapshot is None
    before = len(commands.calls)
    with pytest.raises(InvalidTransition):
        instance.snapshot_and_restart(guard())
    assert len(commands.calls) == before
    instance.stop(guard())
    assert all(g.stopped for g in groups)


def test_cleanup_error_is_retained_and_ports_are_never_released(
    node_path: Path,
) -> None:
    instance, _, groups, _ = case(node_path)
    instance.prepare(guard())
    instance.start(guard())
    groups[0].fail = "stop"
    with pytest.raises(BaseExceptionGroup) as caught:
        instance.stop(guard())
    assert instance.state == "failed" and "original group cleanup failed" in str(
        caught.value.exceptions[0]
    )
    assert instance.lease is not None and Path(instance.files_plan.node_root).exists()


def test_invalid_image_and_foreign_owner_refused_before_staging(
    node_path: Path,
) -> None:
    files = Files()
    selected = spec(node_path / "instance")
    bad = selected.files.model_copy(
        update={"image": selected.files.image.model_copy(update={"sha256": "f" * 64})}
    )
    with pytest.raises(ValueError):
        RedditInstance(
            bad,
            files=files,
            ports=Ports(),
            commands=TreeCommands(node_path),
            services=lambda p, c: pytest.fail("No native effect"),
        )
    assert files.calls == 0
    instance, commands, groups, _ = case(node_path)
    instance.owner = (os.getpid() + 1, instance.owner[1])
    with pytest.raises(OwnershipConflict):
        instance.prepare(guard())
    assert groups == [] and commands.calls == []


def test_cancel_before_prepare_has_no_stage_lease_or_native_effect(
    node_path: Path,
) -> None:
    instance, commands, groups, _ = case(node_path)

    class Cancelled:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        instance.prepare(Cancelled())
    assert (
        instance.state == "new"
        and instance.lease is None
        and groups == []
        and commands.calls == []
    )
