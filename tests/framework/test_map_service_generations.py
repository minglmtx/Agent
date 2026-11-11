"""Whole Map preparation/service combination and original Rails replacement."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.map_frontend_lifecycle import MapFrontendStopped
from lab_generate_skill.domain.native_namespace import NativeNamespaceStopped
from lab_generate_skill.adapters.map_runtime.services import OwnedMapServices
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from lab_generate_skill.sites.map.service_readiness import MapReadiness
from map_service_generations_fixtures import GenerationCase
from map_instance_fixtures import InstanceCase
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


@pytest.fixture
def generations(case: InstanceCase) -> Iterator[GenerationCase]:
    value = GenerationCase(case)
    try:
        value.instance.prepare(guard(60))
        value.instance.start(guard(600))
        yield value
    finally:
        value.close_sockets()


@pytest.mark.parametrize("forced", [False, True])
def test_same_instance_retire_replace_health_and_all_generations_close(
    generations: GenerationCase, forced: bool
) -> None:
    owned = generations.owned
    assert owned is not None and len(owned.records) == 10
    original = owned.active["rails_server"]
    other = dict(owned.active)
    if forced:
        generations.force()
    result = owned.retire_frontend(guard())
    assert result is original.retirement and result.generation == 1
    assert (
        result.namespace.original == original.pin and result.forced_namespace is forced
    )
    assert (original.grace_error is not None) is forced
    assert generations.rails().force_calls == int(forced)
    assert generations.rails().quiet_calls == 1 and generations.rails().close_calls == 1
    assert "rails_server" not in owned.active
    for name, record in other.items():
        if name != "rails_server":
            assert owned.active[name] is record
    with pytest.raises(InvalidTransition):
        owned.retire_frontend(guard())
    with pytest.raises(InvalidTransition):
        owned.start("rails_server", original.argv, guard())
    owned.replace_frontend(guard())
    replacement = owned.active["rails_server"]
    assert (
        replacement.number == 2
        and replacement.argv == original.argv
        and replacement is not original
    )
    spec = generations.case.spec
    MapReadiness(
        spec, generations.case.commands, owned, BoundedMapStartupControls()
    ).http(spec.ports.web, "/", guard(), first_rails=True)
    new_pin = owned.pin_namespace("rails_server", guard())
    assert new_pin != original.pin and new_pin.service == "rails_server"
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    owned.require_running()
    facts = generations.instance.stop(guard())
    assert len(facts) == 11 and len({f.process_id for f in facts}) == 11
    assert owned.stop(guard()) is facts
    assert all(g.close_calls == 1 for g in generations.groups)
    assert generations.case.ports.lease.releases == 0
    assert original.retirement is result and len(owned.records) == 11


@pytest.mark.parametrize(
    "error",
    [
        OperationStopped("CANCELLED", "caller"),
        OperationStopped("DEADLINE_EXCEEDED", "caller"),
        OSError("original TERM error"),
        TimeoutError("unclassified timeout"),
    ],
)
def test_other_stop_errors_never_force_or_replace(
    generations: GenerationCase, error: BaseException
) -> None:
    owned = generations.owned
    assert owned is not None
    rails = generations.rails()
    rails.retire_error = error
    with pytest.raises(type(error)) as caught:
        owned.retire_frontend(guard())
    assert caught.value is error and owned.poisoned and rails.force_calls == 0
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    with pytest.raises(InvalidTransition):
        owned.retire_frontend(guard())
    assert rails.quiet_calls == 1 and len(generations.instance.stop(guard())) == 10


def test_caller_cancellation_at_force_boundary_keeps_grace_error(
    generations: GenerationCase,
) -> None:
    owned = generations.owned
    assert owned is not None
    generations.force()
    error = OperationStopped("CANCELLED", "original-caller")
    original = owned.active["rails_server"]

    class Stop:
        def checkpoint(self) -> float:
            if original.grace_error is not None:
                raise error
            return 90.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped) as caught:
        owned.retire_frontend(Stop())
    assert caught.value is error and original.grace_error is not None
    assert generations.rails().force_calls == 0 and original.retirement is None
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    assert len(generations.instance.stop(guard())) == 10


@pytest.mark.parametrize("phase", ["force", "close"])
def test_uncertain_force_or_handle_close_blocks_replacement(
    generations: GenerationCase, phase: str
) -> None:
    owned = generations.owned
    assert owned is not None
    rails = generations.rails()
    error = OSError("original " + phase + " response unknown")
    if phase == "force":
        generations.force()
        rails.force_error = error
    else:
        rails.close_error = error
    with pytest.raises(OSError) as caught:
        owned.retire_frontend(guard())
    assert caught.value is error and owned.poisoned
    assert owned.active["rails_server"].retirement is None
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    if phase == "close":
        with pytest.raises(BaseExceptionGroup):
            generations.instance.stop(guard())
        assert all(g.close_calls == 1 for g in generations.groups)
        with pytest.raises(InvalidTransition):
            owned.stop(guard())
        assert all(g.close_calls == 1 for g in generations.groups)
    else:
        assert len(generations.instance.stop(guard())) == 10
        assert rails.force_calls == 1


def test_wrong_original_namespace_cannot_retire(generations: GenerationCase) -> None:
    owned = generations.owned
    assert owned is not None
    generations.force()
    rails = generations.rails()
    pin = owned.active["app_postgres"].pin
    assert pin is not None
    rails.force_result = NativeNamespaceStopped(
        original=pin, init_exit_observed=True, launcher_returncode=0
    )
    with pytest.raises(OwnershipConflict):
        owned.retire_frontend(guard())
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    assert len(generations.instance.stop(guard())) == 10


def test_replacement_spawn_reply_unknown_retains_both_generations(
    generations: GenerationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = generations.owned
    assert owned is not None
    owned.retire_frontend(guard())
    factory = owned.factory
    error = OSError("replacement started then reply lost")

    def changed(path: Path) -> Any:
        group = factory(path)
        original = group.start

        def fail(name: str, argv: tuple[str, ...], control: Any) -> None:
            original(name, argv, control)
            raise error

        monkeypatch.setattr(group, "start", fail)
        return group

    monkeypatch.setattr(owned, "factory", changed)
    with pytest.raises(OSError) as caught:
        owned.replace_frontend(guard())
    assert caught.value is error and owned.poisoned and len(owned.records) == 11
    assert owned.active["rails_server"].number == 2
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    assert len(generations.instance.stop(guard())) == 11


@pytest.mark.parametrize(
    "action", ["retire_frontend", "replace_frontend", "stop", "require_running"]
)
def test_foreign_owner_cannot_retire_replace_or_close(
    generations: GenerationCase, action: str
) -> None:
    owned = generations.owned
    assert owned is not None
    args = () if action == "require_running" else (guard(),)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(getattr(owned, action), *args).result()
    assert (
        not owned.poisoned
        and not owned.stopping
        and not generations.rails().quiet_calls
    )
    assert len(generations.instance.stop(guard())) == 10


@pytest.mark.parametrize(
    "name,argv",
    [
        (None, ("/bin/true",)),
        ("", ("/bin/true",)),
        ("../bad", ("/bin/true",)),
        ("x" * 65, ("/bin/true",)),
        ("rails_server", ()),
        ("rails_server", ["/bin/true"]),
        ("rails_server", ("relative",)),
        ("rails_server", ("/bin/true", None)),
        ("rails_server", ("/bin/true", "x\0")),
    ],
)
def test_invalid_launch_has_no_directory_or_factory_effect(
    node_path: Path, name: Any, argv: Any
) -> None:
    root = node_path / "logs"
    root.mkdir(mode=0o700)
    owned = OwnedMapServices(root, BoundedMapStartupControls())
    with pytest.raises(ValueError):
        owned.start(name, argv, guard())
    assert not list(root.iterdir()) and owned.records == [] and owned.attempted == set()
    assert owned.stop(guard()) == ()


def test_no_original_or_live_unretired_replacement_is_rejected(
    generations: GenerationCase, node_path: Path
) -> None:
    owned = generations.owned
    assert owned is not None
    with pytest.raises(InvalidTransition):
        owned.replace_frontend(guard())
    fresh = node_path / "no-services"
    fresh.mkdir(mode=0o700)
    empty = OwnedMapServices(fresh, BoundedMapStartupControls())
    with pytest.raises(InvalidTransition):
        empty.retire_frontend(guard())
    with pytest.raises(InvalidTransition):
        empty.replace_frontend(guard())
    assert empty.records == [] and empty.stop(guard()) == ()
    assert len(generations.instance.stop(guard())) == 10


def test_termination_receipt_refuses_false_force_or_foreign_master(
    generations: GenerationCase,
) -> None:
    owned = generations.owned
    assert owned is not None
    result = owned.retire_frontend(guard())
    raw = result.model_dump()
    with pytest.raises(ValueError):
        MapFrontendStopped.model_validate({**raw, "forced_namespace": True})
    with pytest.raises(ValueError):
        MapFrontendStopped.model_validate(
            {**raw, "grace_timeout_operation_id": "map-frontend_grace"}
        )
    with pytest.raises(ValueError):
        MapFrontendStopped.model_validate({**raw, "generation": 0})
    with pytest.raises(ValueError):
        MapFrontendStopped.model_validate(
            {**raw, "master": {**raw["master"], "process_id": 1}}
        )
    assert len(generations.instance.stop(guard())) == 10


def test_original_grace_force_and_caller_budgets_are_intersected() -> None:
    limits = BoundedMapStartupControls()
    assert limits.bind(guard(120), "frontend_grace").checkpoint() <= 30
    assert limits.bind(guard(120), "frontend_force").checkpoint() <= 10
    assert limits.bind(guard(2), "frontend_grace").checkpoint() <= 2
    assert limits.bind(guard(2), "frontend_force").checkpoint() <= 2
