"""Freeze the origin before staging; stop never releases the worker's lease."""

from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.adapters.network.loopback_ports import PortsUnavailable
from map_instance_fixtures import InstanceCase
from test_map_instance import case as case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_exact_source_origin_keeps_original_lease_through_start_and_stop(
    case: InstanceCase,
) -> None:
    instance = case.build(expected_web_port=case.spec.ports.web)
    assert instance.prepare(guard(60)) == case.spec
    assert len(case.loaded) == 5 and case.ports.calls == 1
    assert instance.start(guard(600)) == case.spec.endpoint
    assert len(instance.stop(guard())) == 10
    assert instance.lease is case.ports.lease and case.ports.lease.releases == 0
    for action in (instance.prepare, instance.start):
        with pytest.raises(InvalidTransition):
            action(guard())


@pytest.mark.parametrize("mode", ["wrong-port", "port-busy", "cancel", "stage-partial"])
def test_fixed_origin_failure_has_no_fallback_or_reissue(
    case: InstanceCase, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    instance = case.build(
        expected_web_port=case.spec.ports.web + (1 if mode == "wrong-port" else 0)
    )
    error: BaseException
    if mode in ("port-busy", "cancel"):
        error = (
            PortsUnavailable("original origin busy")
            if mode == "port-busy"
            else TimeoutError("original port reserve cancelled")
        )

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise error

        monkeypatch.setattr(case.ports, "reserve", refuse)
    elif mode == "stage-partial":
        error = OSError("original stage reply lost")
        original = case.files.stage

        def partial(*args: Any, **kwargs: Any) -> None:
            original(*args, **kwargs)
            raise error

        monkeypatch.setattr(case.files, "stage", partial)
    else:
        error = OwnershipConflict("fixture expected mismatch")
    with pytest.raises(type(error)) as caught:
        instance.prepare(guard(60))
    assert instance.primary_error is caught.value and instance.state == "failed"
    if mode != "wrong-port":
        assert caught.value is error
    assert len(case.loaded) == (5 if mode == "stage-partial" else 0)
    assert not case.factories and instance.frontend is None
    assert (instance.lease is case.ports.lease) == (
        mode in ("wrong-port", "stage-partial")
    )
    with pytest.raises(InvalidTransition):
        instance.prepare(guard())
    assert instance.stop(guard()) == () and case.ports.lease.releases == 0


@pytest.mark.parametrize("bad", [True, "20001", 0, 65536, [], {}])
def test_invalid_expected_origin_precedes_all_effects(
    case: InstanceCase, bad: Any
) -> None:
    with pytest.raises(ValueError):
        case.build(expected_web_port=bad)
    assert not case.loaded and case.ports.calls == 0 and not case.factories
