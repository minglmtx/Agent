"""Exact original master/namespace facts, no force fallback or implicit restart."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from native_quiescence_fixtures import group
from test_slurm_commands import guard


def test_graceful_quiescence_joins_every_original_and_keeps_cleanup_handles(
    tmp_path: Path,
) -> None:
    services, children, held = group(tmp_path)
    result = services.quiesce(guard(5))
    assert isinstance(result, NativeServiceQuiescence)
    assert tuple(x.service for x in result.masters) == ("mysql", "php")
    assert all(x.state == "reaped" and not x.kill_requested for x in result.masters)
    assert all(child.terms == 1 for child in children.values())
    assert all(not pin.closed and pin.stopped is not None for pin in held.values())
    assert not services.killed
    with pytest.raises(RuntimeError):
        services.quiesce(guard(5))
    with pytest.raises(RuntimeError):
        services.require_running()
    with pytest.raises(RuntimeError):
        services.start("other", ("/bin/true",), guard(5))
    assert all(child.terms == 1 for child in children.values())


@pytest.mark.parametrize(
    "change",
    [
        "missing_pin",
        "forced_namespace",
        "closed_pin",
        "forced_master",
        "empty",
        "exited",
    ],
)
def test_invalid_originals_have_no_term_effect(tmp_path: Path, change: str) -> None:
    services, children, held = group(tmp_path)
    if change == "missing_pin":
        del services.namespaces["php"]
    elif change == "forced_namespace":
        held["php"].attempted = True
    elif change == "closed_pin":
        held["php"].closed = True
    elif change == "forced_master":
        services.killed.add("php")
    elif change == "empty":
        services.children.clear()
        services.namespaces.clear()
    elif change == "exited":
        children["php"].returncode = 2
    with pytest.raises(RuntimeError):
        services.quiesce(guard(5))
    assert services.quiescence is None and not any(
        child.terms for child in children.values()
    )


@pytest.mark.parametrize("failure", ["term", "namespace"])
def test_partial_failure_retains_original_facts_and_never_repeats_term(
    tmp_path: Path, failure: str
) -> None:
    services, children, held = group(tmp_path)
    original = TimeoutError("original namespace stop unknown")
    if failure == "term":
        children["php"].failure = original
    else:
        held["php"].failure = original
    with pytest.raises((BaseExceptionGroup, TimeoutError)) as caught:
        services.quiesce(guard(5))
    assert services.quiescence is None
    assert all(child.terms == 1 for child in children.values()) and not any(
        pin.closed for pin in held.values()
    )
    assert getattr(caught.value, "native_service_quiescence") is None
    if failure == "namespace":
        assert (
            caught.value is original
            and len(getattr(original, "native_namespaces_stopped")) == 1
        )
    with pytest.raises(RuntimeError):
        services.quiesce(guard(5))
    assert all(child.terms == 1 for child in children.values())


def test_other_thread_cannot_signal_original_services(tmp_path: Path) -> None:
    services, children, _ = group(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(RuntimeError, match="owner"):
            pool.submit(services.quiesce, guard(5)).result()
    assert not any(child.terms for child in children.values())


@pytest.mark.parametrize(
    "change", ["none", "missing", "duplicate", "pid", "returncode", "killed"]
)
def test_quiescence_contract_matches_original_handles(
    tmp_path: Path, change: str
) -> None:
    services, _, _ = group(tmp_path)
    result = services.quiesce(guard(5))
    if change == "none":
        assert NativeServiceQuiescence.model_validate(result) == result
        return
    if change == "missing":
        result = result.model_copy(update={"namespaces": result.namespaces[:-1]})
    elif change == "duplicate":
        result = result.model_copy(update={"namespaces": (result.namespaces[0],) * 2})
    else:
        field = {
            "pid": "process_id",
            "returncode": "returncode",
            "killed": "kill_requested",
        }[change]
        value = {"pid": 99999, "returncode": 7, "killed": True}[change]
        first = result.masters[0].model_copy(update={field: value})
        result = result.model_copy(update={"masters": (first, *result.masters[1:])})
    with pytest.raises(ValueError):
        NativeServiceQuiescence.model_validate(result)
