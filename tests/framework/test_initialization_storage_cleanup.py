"""Original init failure and unusable evidence storage share one cleanup scope.

CAS/journal/registered owner code is real; only service/kernel/permission edges
are explicit unit doubles. No actual task, new source or recovery grant.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites import step
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from site_physical_authority_fixtures import PhysicalCase, physical_case
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import initialization_case
from test_site_resource import inspect


def failures(error: BaseException) -> list[BaseException]:
    result: list[BaseException] = []
    pending = [error]
    while pending:
        current = pending.pop(0)
        if any(current is item for item in result):
            continue
        result.append(current)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
        primary = getattr(current, "primary", None)
        if isinstance(primary, BaseException):
            pending.append(primary)
        pending.extend(getattr(current, "cleanup_errors", ()))
    return result


@pytest.mark.parametrize("reason", ["CANCELLED", "DEADLINE_EXCEEDED"])
def test_actual_initialization_failure_then_storage_loss_keeps_first_and_stops_original_site(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    primary = OperationStopped(reason, "actual-context-input-read")
    observed: list[Any] = []
    with pytest.raises(BaseExceptionGroup) as caught:
        with initialization_case(node_path, monkeypatch) as c:
            observed.append(c)
            store = c.preparation.original.resource.evidence

            def unavailable(*args: Any, **kwargs: Any) -> Any:
                raise InvalidTransition("Storage instance is not ready")

            def stopped(*args: Any, **kwargs: Any) -> Any:
                monkeypatch.setattr(store, "read", unavailable)
                monkeypatch.setattr(store, "put", unavailable)
                raise primary

            monkeypatch.setattr(c.initialization.contexts.facts, "context", stopped)
            c.start()
    errors = failures(caught.value)
    c = observed[0]
    assert primary in errors
    assert any(isinstance(e, TaskInitializationUnconfirmed) for e in errors)
    assert any(isinstance(e, InvalidTransition) for e in errors)
    assert c.initialization.state.phase == "quarantined"
    assert c.browser.phase == "new" and c.backend.engines == []
    resource = c.preparation.original.resource
    assert len(resource.channels) == 1
    assert resource.channels[0].capture.termination is not None
    assert resource.channels[0].capture.termination.state == "reaped"
    observations = [
        getattr(e, "site_resource_physical_observation")
        for e in errors
        if hasattr(e, "site_resource_physical_observation")
    ]
    assert observations and all(
        not r["durable_resource_close_confirmed"] for r in observations
    )


@pytest.mark.parametrize("stop_failure", [False, True])
def test_original_physical_authority_with_unusable_storage_has_separate_truthful_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_failure: bool
) -> None:
    p: PhysicalCase = physical_case(tmp_path, monkeypatch)
    primary = OperationStopped("DEADLINE_EXCEEDED", "initialization-context")
    original_verify = p.c.authority.verify
    store_lost = False
    original_close = step.observe_closed

    def verify(*args: Any, **kwargs: Any) -> Any:
        if store_lost and args[1] == "close":
            raise InvalidTransition(
                "Storage instance is not ready at original close authority"
            )
        return original_verify(*args, **kwargs)

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise InvalidTransition("Storage instance is not ready")

    def close(*args: Any, **kwargs: Any) -> Any:
        if stop_failure:
            raise TimeoutError("Original physical quiescence unconfirmed")
        return original_close(*args, **kwargs)

    monkeypatch.setattr(p.c.authority, "verify", verify)
    monkeypatch.setattr(step, "observe_closed", close)
    with pytest.raises(BaseExceptionGroup) as caught:
        with p.enter():
            store_lost = True
            monkeypatch.setattr(p.c.evidence, "read", unavailable)
            monkeypatch.setattr(p.c.evidence, "put", unavailable)
            raise primary
    errors = failures(caught.value)
    assert primary in errors and any(isinstance(e, InvalidTransition) for e in errors)
    if stop_failure:
        assert any(isinstance(e, TimeoutError) for e in errors)
    assert p.c.channels[0].aborts == 1
    assert p.c.channels[0].capture.termination is not None
    assert p.c.channels[0].capture.termination.state == "reaped"
    assert p.authority._state.target is not None
    assert p.authority._state.pin is None and p.held[0].closes == 1
    assert p.authority.closed is None and p.c.authority.close_calls == 0
    assert any("target is held but durable closure" in str(e) for e in errors)
    assert inspect(p.c).state == "acquired"
    facts = getattr(caught.value, "site_resource_physical_observation")
    assert (
        not facts["durable_resource_close_confirmed"]
        and not facts["step_closure_evidence_returned"]
    )
