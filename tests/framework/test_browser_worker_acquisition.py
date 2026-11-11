"""Original worker commit precedes navigation; initial readiness remains separate."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.initial_observation import BrowserAcquiredFact
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import ResourceCase, resource_case
from browser_worker_fixtures import UnitBrowser
from test_browser_resource import enter, inspect


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ResourceCase:
    return resource_case(tmp_path, monkeypatch)


def test_registered_worker_fact_is_durable_before_first_navigation(
    c: ResourceCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = UnitBrowser.start
    seen: list[BrowserWorkerAcquiredFact] = []

    def start(engine: UnitBrowser, *args: Any, **kwargs: Any) -> Any:
        record = inspect(c)
        assert record.state == "acquired" and engine.last_readout is None
        reference = record.events[-1].evidence[0]
        assert reference.content_schema == "browser-worker-acquired/1"
        fact = BrowserWorkerAcquiredFact.model_validate_json(c.evidence.read(reference))
        fact.check_spec(c.spec)
        assert fact.details.browser_started is False
        assert (
            c.evidence.read(fact.details.prepared_ref)
            == fact.details.prepared.model_dump_json().encode()
        )
        assert fact.operation == record.events[-1].operation
        seen.append(fact)
        return original(engine, *args, **kwargs)

    monkeypatch.setattr(UnitBrowser, "start", start)
    with enter(c) as session:
        assert len(seen) == 1 and session.resource_started_ref is not None
        record = inspect(c)
        initialized = BrowserAcquiredFact.model_validate_json(
            c.evidence.read(session.resource_started_ref)
        )
        assert initialized.details.worker_acquired_ref == record.events[2].evidence[0]
        assert (
            initialized.details.started.owner_guard
            == seen[0].details.prepared.owner_guard
        )
        assert (
            initialized.details.started.initial_observation_ref
            == session.observation_ref
        )
        assert initialized.details.started.initial_return_ref == session.last_return_ref
        assert len(record.events) == 3  # No invented state/self-transition.
    assert inspect(c).state == "closed"
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))["details"]
    assert session.resource_started_ref is not None
    assert ending["initial_ready_ref"] == session.resource_started_ref.model_dump(
        mode="json"
    )


@pytest.mark.parametrize(
    "fault", ["none", "missing_initial", "wrong_worker", "changed_started"]
)
def test_closed_initial_readback_keeps_original_worker_and_full_initial_fact(
    c: ResourceCase,
    fault: str,
) -> None:
    from source_review_browser import review_browser_initial
    from test_slurm_commands import guard

    with enter(c):
        pass
    record = inspect(c)
    acquired_ref = record.events[2].evidence[0]
    acquired = json.loads(c.evidence.read(acquired_ref))
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))["details"]
    if fault == "missing_initial":
        ending["initial_ready_ref"] = None
    elif fault == "wrong_worker":
        acquired_ref = acquired_ref.model_copy(update={"producer": "foreign"})
    elif fault == "changed_started":
        ending["attempt"]["started"]["installed_sources"]["manifest_sha256"] = "f" * 64
    if fault == "none":
        result = review_browser_initial(
            c.spec.model_dump(mode="json"),
            acquired,
            ending,
            acquired_ref,
            c.evidence,
            guard(),
        )
        assert result.model_dump(mode="json") == ending["attempt"]["started"]
    else:
        with pytest.raises((EvidenceIntegrityError, ValidationError)):
            review_browser_initial(
                c.spec.model_dump(mode="json"),
                acquired,
                ending,
                acquired_ref,
                c.evidence,
                guard(),
            )


@pytest.mark.parametrize(
    "fault", ["before_commit", "after_commit", "wrong_ack", "cancelled"]
)
def test_unconfirmed_original_worker_commit_never_starts_browser(
    c: ResourceCase,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    advance = c.journal.advance
    primary = (
        OperationStopped("CANCELLED", "browser-worker-acquired")
        if fault == "cancelled"
        else OSError("original acquired commit unconfirmed")
    )

    def commit(
        token: AllocationToken,
        state: ResourceState,
        refs: tuple[EvidenceRef, ...],
        revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        if state != "acquired":
            return advance(token, state, refs, revision, op)
        if fault in ("before_commit", "cancelled"):
            raise primary
        recorded = advance(token, state, refs, revision, op)
        if fault == "after_commit":
            raise primary
        return recorded.model_copy(
            update={"token": token.model_copy(update={"allocation_id": "foreign"})}
        )

    monkeypatch.setattr(c.journal, "advance", commit)
    expected = ValidationError if fault == "wrong_ack" else type(primary)
    with pytest.raises(expected):
        with enter(c):
            pytest.fail("Unconfirmed acquisition must not yield a session")
    assert "start" not in c.channels[0].engine.calls
    assert c.channels[0].engine.last_readout is None
    assert c.channels[0].capture.termination is not None
    record = inspect(c)
    assert record.state == "closed"
    assert ("acquired" in [e.state for e in record.events]) == (
        fault in ("after_commit", "wrong_ack")
    )


def test_lost_initial_ready_publication_retains_original_worker_and_return(
    c: ResourceCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    put = c.evidence.put
    candidates: list[EvidenceRef] = []
    primary = OSError("initial readiness acknowledgement lost")

    def publish(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        ref = put(data, metadata, control=control)
        if (
            metadata.content_schema == "browser-resource-fact/1"
            and "started" in json.loads(data).get("details", {})
        ):
            candidates.append(ref)
            raise primary
        return ref

    monkeypatch.setattr(c.evidence, "put", publish)
    with pytest.raises(OSError) as caught:
        with enter(c):
            pytest.fail("Lost initial publication must not grant a session")
    assert caught.value is primary and len(candidates) == 1
    assert c.channels[0].engine.calls == ["start", "close"]
    record = inspect(c)
    assert record.state == "closed"
    initial = BrowserAcquiredFact.model_validate_json(c.evidence.read(candidates[0]))
    assert initial.details.worker_acquired_ref == record.events[2].evidence[0]
    assert getattr(primary, "browser_resource_readout").observation.sequence == 0


@pytest.mark.parametrize(
    "changed",
    [
        "empty",
        "wrong_type",
        "started",
        "numeric_false",
        "missing_ref",
        "foreign_ref",
        "foreign_spec",
    ],
)
def test_pre_navigation_fact_requires_complete_exact_original_identity(
    c: ResourceCase, changed: str
) -> None:
    with enter(c):
        raw = json.loads(c.evidence.read(inspect(c).events[2].evidence[0]))
    if changed == "empty":
        raw = {}
    elif changed == "wrong_type":
        raw = []
    elif changed == "started":
        raw["details"]["browser_started"] = True
    elif changed == "numeric_false":
        raw["details"]["browser_started"] = 0
    elif changed == "missing_ref":
        del raw["details"]["prepared_ref"]
    elif changed == "foreign_ref":
        raw["details"]["prepared_ref"]["sha256"] = "f" * 64
    else:
        raw["spec_sha256"] = "f" * 64
    from lab_generate_skill.domain.errors import OwnershipConflict

    with pytest.raises((ValidationError, OwnershipConflict)):
        BrowserWorkerAcquiredFact.model_validate(raw).check_spec(c.spec)
