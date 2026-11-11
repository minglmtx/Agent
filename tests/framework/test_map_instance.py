"""Instance composition and retention across original partial initialization/stop."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.service_commands import SERVICE_NAMES
from map_frontend_fixtures import originals
from map_instance_fixtures import InstanceCase
from site_instance_fixtures import node_path
from test_slurm_commands import guard


@pytest.fixture
def case(node_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[InstanceCase]:
    value = InstanceCase(node_path, monkeypatch)
    try:
        yield value
    finally:
        value.close_sockets()


def test_published_inputs_to_original_ten_services_and_retained_close(
    case: InstanceCase,
) -> None:
    instance = case.instance
    assert instance.prepare(guard(60)) == case.spec
    assert len(case.loaded) == 5 and case.ports.calls == 1
    assert instance.frontend is not None and instance.frontend.receipt is not None
    assert (
        instance.frontend.state == "prepared"
        and len(instance.frontend.receipt.changed) == 7
    )
    assert instance.start(guard(600)) == case.spec.endpoint
    assert instance.state == "ready" and instance.group is case.group
    assert instance.generation is not None and len(instance.generation.pins) == 10
    assert tuple(case.group.names) == SERVICE_NAMES
    facts = instance.stop(guard())
    assert len(facts) == 10 and all(f.state == "reaped" for f in facts)
    assert instance.stop(guard()) is facts and instance.state == "stopped"
    assert instance.primary_error is None and instance.cleanup_error is None
    assert instance.lease is case.ports.lease and case.ports.lease.releases == 0
    assert Path(case.spec.inputs.files.node_root).is_dir()
    assert len(case.factories) == 1
    for action in (instance.prepare, instance.start):
        with pytest.raises(InvalidTransition):
            action(guard())
    source = Path(
        next(t.source_root for t in case.spec.inputs.trees if t.role == "frontend")
    )
    for name, body in originals().items():
        assert (source / name).read_bytes() == body
    # These are bind targets, not the real DB or persistent frontend host paths.
    assert not list((Path(case.spec.state_root("frontend")) / "pg").iterdir())
    assert (
        Path(case.spec.inputs.node_tree("app")) / "postgres/PG_VERSION"
    ).read_bytes() == b"11\n"
    assert (Path(case.spec.inputs.node_tree("frontend")) / "storage").is_dir()


@pytest.mark.parametrize("phase", ["stage", "lease", "layout", "frontend"])
def test_prepare_failure_keeps_original_handles_no_reissue(
    case: InstanceCase, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    instance = case.instance
    target, method = {
        "stage": (case.files, "stage"),
        "lease": (case.ports, "reserve"),
        "layout": (case.layout, "prepare"),
        "frontend": (case.frontend, "apply"),
    }[phase]
    original = getattr(target, method)
    error = OSError("original " + phase + " reply lost")
    calls = 0

    def fail(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        # reserve guarantees rollback when it cannot return its original lease.
        # Its refusal is before acquisition; the other phases lose a reply after effect.
        if phase != "lease":
            original(*args, **kwargs)
        raise error

    monkeypatch.setattr(target, method, fail)
    with pytest.raises(OSError) as caught:
        instance.prepare(guard(60))
    assert (
        caught.value is error
        and instance.primary_error is error
        and instance.state == "failed"
    )
    assert calls == 1 and len(case.loaded) == 5 and not case.factories
    assert Path(case.spec.inputs.files.node_root).exists()
    assert (instance.lease is case.ports.lease) == (phase in ("layout", "frontend"))
    if phase == "frontend":
        assert instance.frontend is not None and instance.frontend.state == "failed"
        assert (
            Path(case.spec.inputs.files.node_root)
            / "frontend-preparation/prepared.json"
        ).exists()
    for action in (instance.prepare, instance.start):
        with pytest.raises(InvalidTransition):
            action(guard())
    assert instance.stop(guard()) == () and instance.primary_error is error
    assert case.ports.lease.releases == 0 and calls == 1


@pytest.mark.parametrize(
    "ports",
    [
        (),
        (12001,) * 6,
        (12001,) * 5,
        (12001,) * 7,
        [12001, 12002, 12003, 12004, 12005, 12006],
        None,
        (True, 12002, 12003, 12004, 12005, 12006),
        (0, 12002, 12003, 12004, 12005, 12006),
        (65536, 12002, 12003, 12004, 12005, 12006),
    ],
)
def test_invalid_lease_never_prepares_or_loses_original_lease(
    case: InstanceCase, ports: Any
) -> None:
    case.ports.lease.ports = ports
    with pytest.raises(ValueError):
        case.instance.prepare(guard(60))
    assert case.instance.lease is case.ports.lease and case.instance.spec is None
    assert not list(Path(case.spec.inputs.files.state_root).iterdir())
    assert case.instance.frontend is None and not case.factories
    assert case.instance.stop(guard()) == () and case.ports.lease.releases == 0


@pytest.mark.parametrize(
    "changes",
    [
        dict(hostname=""),
        dict(hostname=None),
        dict(hostname="node\n"),
        dict(hostname="x" * 254),
        dict(host_cpus=0),
        dict(host_cpus=True),
        dict(host_cpus="128"),
        dict(host_cpus=None),
        dict(inputs=None),
        dict(inputs={}),
    ],
)
def test_invalid_instance_inputs_precede_effects(
    case: InstanceCase, changes: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        case.build(**changes)
    assert not case.loaded and not case.factories and case.ports.calls == 0
    assert not Path(case.spec.inputs.files.node_root).exists()


@pytest.mark.parametrize("setup,started", [("search_refresh", 1), ("bundle_check", 9)])
def test_partial_service_failure_keeps_group_and_independent_cleanup(
    case: InstanceCase, setup: str, started: int
) -> None:
    instance = case.instance
    instance.prepare(guard(60))
    case.commands.fail = setup
    with pytest.raises(OSError) as caught:
        instance.start(guard(600))
    assert (
        caught.value is case.commands.error and instance.primary_error is caught.value
    )
    assert instance.state == "failed" and instance.group is case.group
    assert len(case.group.names) == started
    assert instance.generation is not None and instance.generation.state == "failed"
    with pytest.raises(InvalidTransition):
        instance.start(guard())
    assert len(instance.stop(guard())) == started
    assert (
        case.ports.lease.releases == 0 and instance.primary_error is case.commands.error
    )


def test_spawn_committed_then_unknown_keeps_original_group(
    case: InstanceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = case.instance
    instance.prepare(guard(60))
    original = case.group.start
    error = OSError("spawn completed but reply unknown")

    def fail(name: str, argv: tuple[str, ...], control: OperationControl) -> None:
        original(name, argv, control)
        raise error

    monkeypatch.setattr(case.group, "start", fail)
    with pytest.raises(OSError) as caught:
        instance.start(guard())
    assert caught.value is error and case.group.names == ["search_postgres"]
    assert instance.generation is not None and instance.generation.pins == ()
    assert len(instance.stop(guard())) == 1 and case.ports.lease.releases == 0


def test_cleanup_failure_retains_both_errors_and_never_replays_stop(
    case: InstanceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = case.instance
    instance.prepare(guard(60))
    case.commands.fail = "search_refresh"
    with pytest.raises(OSError):
        instance.start(guard())
    error = OSError("stop confirmed then receipt lost")
    original = case.group.stop
    calls = 0

    def fail(control: OperationControl) -> Any:
        nonlocal calls
        calls += 1
        original(control)
        raise error

    monkeypatch.setattr(case.group, "stop", fail)
    with pytest.raises(OSError) as caught:
        instance.stop(guard())
    assert caught.value is error and instance.cleanup_error is error
    assert instance.primary_error is case.commands.error and instance.stop_facts is None
    assert instance.group is case.group and instance.state == "failed"
    with pytest.raises(InvalidTransition) as repeat:
        instance.stop(guard())
    assert (
        repeat.value.__cause__ is error
        and calls == 1
        and case.ports.lease.releases == 0
    )


def test_cancellation_after_lease_keeps_lease_and_no_service(
    case: InstanceCase,
) -> None:
    class Stop:
        def checkpoint(self) -> float:
            if case.ports.calls:
                raise TimeoutError("original cancelled after lease")
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        case.instance.prepare(Stop())
    assert case.instance.lease is case.ports.lease and not case.factories
    assert case.instance.state == "failed"
    assert case.instance.stop(guard()) == () and case.ports.lease.releases == 0


def test_cancellation_before_effect_leaves_new_instance(case: InstanceCase) -> None:
    class Stop:
        def checkpoint(self) -> float:
            raise TimeoutError("already cancelled")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        case.instance.prepare(Stop())
    assert case.instance.state == "new" and not case.loaded and case.ports.calls == 0


@pytest.mark.parametrize("action", ["prepare", "start", "stop"])
def test_foreign_worker_thread_cannot_change_instance(
    case: InstanceCase, action: str
) -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(getattr(case.instance, action), guard()).result()
    assert (
        case.instance.state == "new"
        and not case.loaded
        and not case.instance.stop_attempted
    )


def test_start_without_prepare_and_stop_without_resources(case: InstanceCase) -> None:
    with pytest.raises(InvalidTransition):
        case.instance.start(guard())
    assert case.instance.stop(guard()) == () and not case.loaded
    with pytest.raises(InvalidTransition):
        case.instance.prepare(guard())


@pytest.mark.parametrize("change", ["alias", "mode", "occupied"])
def test_invalid_logs_prevent_service_factory(case: InstanceCase, change: str) -> None:
    instance = case.instance
    instance.prepare(guard(60))
    root = Path(instance.inputs.files.log_root)
    if change == "alias":
        target = root.with_name("saved-logs")
        root.rename(target)
        root.symlink_to(target, target_is_directory=True)
    elif change == "mode":
        root.chmod(0o755)
    else:
        (root / "generation-1").mkdir()
    with pytest.raises((OwnershipConflict, FileExistsError)):
        instance.start(guard())
    assert instance.state == "failed" and not case.factories and instance.group is None
    assert instance.stop(guard()) == () and instance.lease is case.ports.lease


def test_cancellation_after_group_construction_retains_group_without_spawn(
    case: InstanceCase,
) -> None:
    instance = case.instance
    instance.prepare(guard(60))

    class Stop:
        def checkpoint(self) -> float:
            if case.factories:
                raise TimeoutError("cancelled after original group construction")
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        instance.start(Stop())
    assert instance.group is case.group and instance.generation is not None
    assert instance.generation.state == "new" and case.group.names == []
    assert instance.stop(guard()) == () and case.group.stopped
    assert case.ports.lease.releases == 0


def test_service_factory_failure_retains_prepared_root_and_lease(
    case: InstanceCase,
) -> None:
    error = OSError("failed to construct original service group")
    calls = 0

    def fail(root: str, control: OperationControl) -> Any:
        nonlocal calls
        calls += 1
        assert Path(root).is_dir()
        raise error

    instance = case.build(services=fail)
    instance.prepare(guard(60))
    with pytest.raises(OSError) as caught:
        instance.start(guard())
    assert caught.value is error and instance.group is None and calls == 1
    assert instance.lease is case.ports.lease
    with pytest.raises(InvalidTransition):
        instance.start(guard())
    assert instance.stop(guard()) == () and case.ports.lease.releases == 0
