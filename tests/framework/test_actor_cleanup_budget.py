"""Metadata uses its declared budget; physical shutdown stays independently bounded."""

from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_resource_fixtures import ResourceCase, resource_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_actor_resource import inspect
from lab_generate_skill.domain.errors import OperationStopped, InvalidTransition


@pytest.fixture
def c(tmp_path: Path, installed_sources: InstalledFixture) -> ResourceCase:
    return resource_case(
        tmp_path, installed_sources.executable, installation=installed_sources
    )


def test_declared_metadata_budget_reaches_original_actor_closure(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_put = c.evidence.put
    budgets: list[float] = []
    physical: list[float] = []

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        if (
            metadata.content_schema == "actor-resource-fact/1"
            and json.loads(data).get("kind") == "closing"
        ):
            assert control is not None
            budgets.append(control.checkpoint())
            assert budgets[-1] > 60
        return original_put(data, metadata, control)

    monkeypatch.setattr(c.evidence, "put", put)
    original_operation = c.op
    with registered_actor(
        c.spec, c.op, cleanup_seconds=120, **c.dependencies()
    ) as engine:
        close = engine.close

        def bounded(control: OperationControl) -> None:
            physical.append(control.checkpoint())
            assert 0 < physical[-1] <= 10
            close(control)

        monkeypatch.setattr(engine, "close", bounded)
        assert inspect(c).state == "acquired"
    record = inspect(c)
    assert record.state == "closed" and c.op == original_operation
    assert len(budgets) == len(physical) == 1
    assert (
        record.events[-1].operation.deadline - c.clock.utcnow()
    ).total_seconds() > 60


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_initialized_model_task_failure_keeps_storage_available_for_original_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    original_put = c.evidence.put
    primary = OperationStopped(reason, "original-task-initial-baseline")
    after_failure = False
    quarantined = False
    budgets: list[float] = []

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        nonlocal quarantined
        if after_failure:
            assert control is not None
            budgets.append(control.checkpoint())
            # Reproduce the original managed store's fail-closed outcome when
            # an I/O budget cannot cover its metadata exchange. No real sleep.
            if quarantined or budgets[-1] < 10:
                quarantined = True
                raise InvalidTransition("Original diagnostic exchange unconfirmed")
        return original_put(data, metadata, control)

    monkeypatch.setattr(c.evidence, "put", put)
    with pytest.raises(OperationStopped) as caught:
        with registered_actor(c.spec, c.op, cleanup_seconds=120, **c.dependencies()):
            assert inspect(c).state == "acquired"
            after_failure = True
            raise primary
    assert caught.value is primary and not quarantined
    assert budgets and min(budgets) > 60
    record = inspect(c)
    assert record.state == "closed"
    ended = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert ended["primary"]["type_name"] == "OperationStopped"
    assert ended["cleanup_errors"] == [] and ended["step_closed"] is not None


@pytest.mark.parametrize("seconds", [None, True, 0, -1, 3601, "30", 1.5])
def test_illegal_budget_rejected_before_registration_or_authority(
    c: ResourceCase, seconds: Any
) -> None:
    with pytest.raises(ValueError, match="duration"):
        with registered_actor(
            c.spec, c.op, cleanup_seconds=seconds, **c.dependencies()
        ):
            pytest.fail("Invalid cleanup policy entered Actor")
    assert not list(c.journal._root.iterdir())
    assert not c.authority.workers
