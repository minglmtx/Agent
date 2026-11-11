"""Registered acquisition through the actual installed fixed child, no GPU loading."""

from pathlib import Path
import json
import uuid
from datetime import datetime, timedelta, timezone
from collections.abc import Iterator
import pytest
from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    AllocationToken,
    ResourceRecord,
    ResourceState,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_resource_fixtures import resource_case, ResourceCase
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


@pytest.fixture
def c(tmp_path: Path, installed_sources: InstalledFixture) -> ResourceCase:
    return resource_case(
        tmp_path, installed_sources.executable, installation=installed_sources
    )


def inspect(c: ResourceCase) -> ResourceRecord:
    op = c.op.cleanup(
        "inspect-" + uuid.uuid4().hex, now=datetime.now(timezone.utc), seconds=30
    )
    return c.journal.read(c.spec.token, op)


def errors(error: BaseException) -> Iterator[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            yield from errors(child)
    else:
        yield error


def test_real_registered_entry_and_close_and_repeat_rejection(c: ResourceCase) -> None:
    with registered_generator(c.spec, c.op, **c.dependencies()) as engine:
        worker = engine.configure(c.controls.bind(c.op))
        assert worker == c.authority.workers[0]
        assert inspect(c).state == "acquired"
        assert engine.installed_sources is not None
        acquired = inspect(c).events[-1]
        fact = json.loads(c.evidence.read(acquired.evidence[0]))
        assert fact["installed_sources"] == engine.installed_sources.model_dump(
            mode="json"
        )
        assert fact["installed_sources"]["manifest_sha256"] == c.spec.release_ref.sha256
        assert engine.owner_guard is not None
        assert fact["owner_guard"] == engine.owner_guard.model_dump(mode="json")
        assert engine.owner_guard.controller == c.spec.slurm.allocation.facts.writer
        assert engine.owner_guard.worker == worker
    record = inspect(c)
    assert [e.state for e in record.events] == [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]
    assert (
        engine.capture.termination is not None
        and engine.capture.termination.returncode == 0
    )
    with pytest.raises(DispatchAlreadyCommitted):
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("second launch")
    assert len(c.authority.workers) == 1 and inspect(c) == record


def test_denied_admission_has_no_resource_events(c: ResourceCase) -> None:
    c.authority.start_denied = True
    with pytest.raises(PermissionError):
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("denied launch")
    assert not list(c.journal._root.iterdir())


def test_lost_begin_ack_never_starts_or_closes_another_resource(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin = c.journal.begin_acquire

    def lost(
        token: AllocationToken,
        intent_ref: EvidenceRef,
        expected_revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        begin(token, intent_ref, expected_revision, op)
        raise OSError("lost begin acknowledgement")

    monkeypatch.setattr(c.journal, "begin_acquire", lost)

    def no_start(self: FramedProcessSession, control: OperationControl) -> None:
        pytest.fail("spawn before acknowledged intent")

    monkeypatch.setattr(FramedProcessSession, "start", no_start)
    with pytest.raises(OSError):
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("lost ack")
    assert inspect(c).state == "acquiring"
    assert not c.authority.closed


def test_body_error_is_preserved_after_independent_close(c: ResourceCase) -> None:
    original = ValueError("body failed")
    with pytest.raises(ValueError) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            raise original
    assert caught.value is original and inspect(c).state == "closed"
    assert getattr(original, "command_capture").termination.state == "reaped"


@pytest.mark.parametrize("phase", ["acquired", "closing"])
def test_bookkeeping_failure_cannot_skip_physical_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    advance = c.journal.advance

    def fail(
        token: AllocationToken,
        state: ResourceState,
        evidence: tuple[EvidenceRef, ...],
        revision: int,
        op: OperationContext,
    ) -> ResourceRecord:
        if state == phase:
            raise OSError("injected " + phase + " failure")
        return advance(token, state, evidence, revision, op)

    monkeypatch.setattr(c.journal, "advance", fail)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pass
    assert any("injected " + phase in str(e) for e in errors(caught.value))
    assert c.authority.closed and c.authority.closed[0].state == "reaped"
    assert inspect(c).state == ("closed" if phase == "acquired" else "acquired")


def test_unconfirmed_closure_is_quarantined_and_preserves_primary(
    c: ResourceCase,
) -> None:
    c.authority.close_denied = True
    original = ValueError("body failed")
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            raise original
    assert list(errors(caught.value))[0] is original
    assert any(isinstance(e, PermissionError) for e in errors(caught.value))
    assert inspect(c).state == "quarantined"


def test_wrong_child_handshake_stops_original_process(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure = SupervisedGeneratorEngine.configure

    def wrong(
        self: SupervisedGeneratorEngine, control: OperationControl
    ) -> ProcessIdentity:
        return configure(self, control).model_copy(update={"process_id": 1})

    monkeypatch.setattr(SupervisedGeneratorEngine, "configure", wrong)
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("wrong child accepted")
    assert any(isinstance(e, EvidenceIntegrityError) for e in errors(caught.value))
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
    assert inspect(c).state == "quarantined"


def test_expired_body_uses_new_cleanup_deadline(c: ResourceCase) -> None:
    with registered_generator(c.spec, c.op, **c.dependencies()):
        # Only the execute clock expires; cleanup is a fresh parent-linked op.
        c.controls.bind(c.op)._expires = -1
    assert inspect(c).state == "closed"


def test_clock_failure_during_cleanup_still_reaps_child(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):

            def broken_clock() -> datetime:
                raise OSError("cleanup clock failed")

            monkeypatch.setattr(c.clock, "utcnow", broken_clock)
    assert any("cleanup clock failed" in str(e) for e in errors(caught.value))
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
