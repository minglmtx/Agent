"""Separate immutable lifetime, acquisition identity and independent shutdown."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.browsergym.collection_control import (
    OriginalMapCollectionControl,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.map_browser_collection import MapBrowserCollectionSpec
from lab_generate_skill.ports.lifecycle import OperationControl
from map_browser_collection_fixtures import CollectionCase
from map_route_fixtures import collection, Route, readout
from test_slurm_commands import guard


class SwitchControl:
    def __init__(self) -> None:
        self.stopped = False

    def checkpoint(self) -> float:
        if self.stopped:
            raise OperationStopped("DEADLINE_EXCEEDED", "original-collection")
        return 600.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CollectionCase:
    return CollectionCase(tmp_path, monkeypatch)


def declared(c: CollectionCase) -> MapBrowserCollectionSpec:
    assert c.configuration.map_inputs is not None
    spec = c.configuration.map_inputs.collection
    return MapBrowserCollectionSpec.model_validate(
        spec.model_copy(
            update={
                "lifetime_operation": spec.lifetime_operation.model_copy(
                    update={
                        "deadline": spec.operation.deadline + timedelta(seconds=600)
                    }
                )
            }
        )
    )


def test_original_lifetime_survives_shorter_acquisition_without_renewal(
    c: CollectionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = declared(c)

    class Clock:
        def utcnow(self) -> datetime:
            return spec.operation.deadline + timedelta(seconds=1)

        def monotonic(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            raise AssertionError("Original deadline construction must not wait")

    with pytest.raises(ValueError):
        OriginalMapCollectionControl(spec.operation, Clock())
    lifetime = OriginalMapCollectionControl(spec.lifetime_operation, Clock())
    original_expiry = lifetime.bound._expires
    assert 0 < lifetime.checkpoint() <= 599
    assert lifetime.intersect(guard(20)).checkpoint() <= 20
    assert lifetime.bound._expires == original_expiry
    caller = SwitchControl()
    caller.stopped = True
    with pytest.raises(OperationStopped):
        lifetime.intersect(caller).checkpoint()
    monkeypatch.setattr(lifetime.bound, "_expires", -1.0)
    for _ in range(2):
        with pytest.raises(OperationStopped):
            lifetime.intersect(guard(86400)).checkpoint()
    assert spec.operation.deadline < spec.lifetime_operation.deadline
    assert MapBrowserCollectionSpec.model_validate_json(spec.model_dump_json()) == spec


@pytest.mark.parametrize(
    "fault",
    [
        "legacy",
        "missing",
        "none",
        "empty",
        "list",
        "text",
        "integer",
        "boolean",
        "run",
        "owner",
        "attempt",
        "allocation",
        "recovery",
        "cancellation",
        "cleanup",
        "same-id",
        "no-parent",
        "self-parent",
        "shorter",
    ],
)
def test_invalid_lifetime_refused_before_collection_effects(
    c: CollectionCase, fault: str
) -> None:
    spec = declared(c)
    data = spec.model_dump(mode="json")
    values: dict[str, Any] = {
        "none": None,
        "empty": {},
        "list": [],
        "text": "lifetime",
        "integer": 1,
        "boolean": True,
    }
    if fault == "legacy":
        data["schema_version"] = "map-browser-collection-spec/1"
    elif fault == "missing":
        del data["lifetime_operation"]
    elif fault in values:
        data["lifetime_operation"] = values[fault]
    else:
        life = data["lifetime_operation"]
        fields = {
            "run": "run_id",
            "owner": "owner_id",
            "attempt": "attempt_id",
            "allocation": "allocation_id",
        }
        if fault in fields:
            life[fields[fault]] = "foreign"
        elif fault == "recovery":
            life["recovery_ref"]["sha256"] = "f" * 64
        elif fault == "cancellation":
            life["cancellation_ref"] = life["recovery_ref"]
        elif fault == "cleanup":
            life["mode"] = "cleanup"
        elif fault == "same-id":
            life["operation_id"] = spec.operation.operation_id
        elif fault == "no-parent":
            life["parent_operation_id"] = None
        elif fault == "self-parent":
            life["parent_operation_id"] = life["operation_id"]
        else:
            life["deadline"] = (
                spec.operation.deadline - timedelta(microseconds=1)
            ).isoformat()
    with pytest.raises(ValidationError):
        MapBrowserCollectionSpec.model_validate_json(json.dumps(data))
    assert not c.resource.channels and not c.calls
    inputs = c.configuration.map_inputs
    assert inputs is not None and not Path(inputs.plan.private_root).exists()


@pytest.mark.parametrize("registered", [False, True])
def test_expired_business_control_still_closes_once_without_dispatch(
    tmp_path: Path, registered: bool
) -> None:
    native, writer, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    lifetime = SwitchControl()
    native.relay.evidence_control = lifetime
    native.attach(page, spec, guard())
    native.observe(page, readout(spec, 0), guard())
    if registered:
        route = Route(native.relay.origin)
        page.handler(route)
        assert len(route.calls) == 1 and not route.aborts
    lifetime.stopped = True
    with pytest.raises(OperationStopped):
        native.before_action(lifetime)
    native.close(guard(20))
    before = sorted(p.name for p in writer.working.iterdir())
    native.close(guard(20))
    assert sorted(p.name for p in writer.working.iterdir()) == before
    assert native.relay.physical_closed and native.state == "closed"
    closing = json.loads((writer.working / "map-process-close.json").read_bytes())
    assert (
        not closing["cleanup_errors"] and not closing["task_success_or_admission_claim"]
    )
    assert all(not job.started for job in native.relay.requests.values())
    if registered:
        raw = json.loads(
            (writer.working / "request-0-never-requested.json").read_bytes()
        )
        assert raw["status"] == "unknown" and raw["native_dispatches"] == 0


def test_expired_close_write_failure_is_retained_and_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native, writer, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    lifetime = SwitchControl()
    native.relay.evidence_control = lifetime
    native.attach(page, spec, guard())
    native.observe(page, readout(spec, 0), guard())
    lifetime.stopped = True
    attempted: list[str] = []

    def fail(name: str, data: bytes, control: OperationControl) -> Any:
        control.checkpoint()
        attempted.append(name)
        raise OSError("Original cleanup write unconfirmed")

    monkeypatch.setattr(writer, "retain", fail)
    with pytest.raises(ExceptionGroup):
        native.close(guard(20))
    assert native.cleanup_errors and native.state == "failed"
    first = list(attempted)
    with pytest.raises(ExceptionGroup):
        native.close(guard(20))
    assert attempted == first == ["map-process-close.json"]
    assert native.relay.physical_closed
