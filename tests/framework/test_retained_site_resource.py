"""Original site RPC/journal/CAS; kernel/native effects are explicit unit doubles."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch
from site_resource_fixtures import Case, resource_case
from test_site_resource import inspect


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Case:
    return resource_case(tmp_path, monkeypatch)


def owner(c: Case) -> RetainedSiteResource:
    return RetainedSiteResource(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
    )


def close(c: Case, held: RetainedSiteResource) -> ResourceRecord:
    op = c.op.cleanup(
        "retained-site-test-close", now=datetime.now(timezone.utc), seconds=30
    )
    return held.close(op, c.controls.bind(op))


def test_pure_scope_then_original_acquisition_and_readonly_close(c: Case) -> None:
    held = owner(c)
    with held.scope():
        assert held.phase == "new" and not c.channels
        with pytest.raises(OwnershipConflict):
            _ = held.site
        live = held.open(c.controls.bind(c.op))
        assert held.site == live.site and held.tasks is live.tasks
        assert held.capture is live.capture and held.resume is live.resume
        assert inspect(c).state == "acquired"
        with pytest.raises(DispatchAlreadyCommitted):
            held.open(c.controls.bind(c.op))
    assert held.phase == "closed" and held.closed == inspect(c)
    assert c.channels[0].engine.calls == ["start", "stop"]
    assert close(c, held) == inspect(c)
    assert len(c.channels) == c.channels[0].starts == 1
    assert held.site == live.site
    with pytest.raises(OwnershipConflict):
        _ = held.tasks


def test_pure_scope_does_not_fabricate_nonstart_closure(c: Case) -> None:
    held = owner(c)
    with held.scope():
        pass
    assert held.phase == "new" and held.closed is None and not c.channels
    with pytest.raises(DispatchAlreadyCommitted):
        close(c, held)


def test_declared_site_cleanup_also_bounds_automatic_original_close_read(
    c: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ManualClock()
    clock.wall = datetime.now(timezone.utc)
    controls = OperationGuards(clock, CancelSwitch())
    held = RetainedSiteResource(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=controls,
        clock=clock,
        authority=c.authority,
        cleanup_seconds=90,
    )
    original = c.authority.verify_closed

    def slow_confirmation(*args: Any, **kwargs: Any) -> ClosureReceipt:
        result = original(*args, **kwargs)
        clock.sleep(35)
        return result

    monkeypatch.setattr(c.authority, "verify_closed", slow_confirmation)
    with held.scope():
        held.open(controls.bind(c.op))
    assert clock.elapsed == 35
    assert held.phase == "closed" and held.closed == inspect(c)
    assert c.channels[0].engine.calls == ["start", "stop"]


def test_consumer_failure_is_distinct_from_confirmed_resource_close(c: Case) -> None:
    held, primary = owner(c), TimeoutError("original consumer failed")
    with pytest.raises(TimeoutError) as caught:
        with held.scope():
            held.open(c.controls.bind(c.op))
            raise primary
    assert caught.value is primary and held.closed == inspect(c)
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
    assert ending["details"]["primary"] is not None
    assert ending["details"]["cleanup_errors"] == []
    assert held.phase == "closed"


def test_partial_start_uses_original_ending_without_manager_exit_again(c: Case) -> None:
    held = owner(c)
    c.authority.deny = "started"
    with pytest.raises(PermissionError) as caught:
        with held.scope():
            held.open(c.controls.bind(c.op))
    assert held.open_error is caught.value and held.phase == "closed"
    assert inspect(c).state == "closed"
    assert c.channels[0].engine.calls == ["start", "stop"]
    with pytest.raises(DispatchAlreadyCommitted):
        held.open(c.controls.bind(c.op))


def test_lost_begin_ack_never_launches_or_guesses_close(
    c: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    held, original = owner(c), c.journal.begin_acquire
    primary = OSError("original acquire acknowledgement lost")

    def lost(*args: Any, **kwargs: Any) -> ResourceRecord:
        original(*args, **kwargs)
        raise primary

    monkeypatch.setattr(c.journal, "begin_acquire", lost)
    with pytest.raises(BaseExceptionGroup):
        with held.scope():
            held.open(c.controls.bind(c.op))
    assert held.open_error is primary and held.closed is None
    assert held.phase == "close-unconfirmed" and inspect(c).state == "acquiring"
    assert c.channels == [] or all(x.starts == 0 for x in c.channels)
    with pytest.raises(DispatchAlreadyCommitted):
        held.open(c.controls.bind(c.op))


def test_post_acquire_cancel_retains_owned_site_for_original_close(c: Case) -> None:
    held = owner(c)

    class CancelAfterReturn:
        count = 0

        def checkpoint(self) -> float:
            self.count += 1
            if self.count == 2:
                raise TimeoutError("cancel after actual startup return")
            return 30.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        with held.scope():
            held.open(CancelAfterReturn())
    assert held.phase == "closed" and held.closed == inspect(c)
    assert c.channels[0].engine.calls == ["start", "stop"]


def test_unconfirmed_original_close_never_reexits_or_reacquires(c: Case) -> None:
    held = owner(c)
    c.authority.deny = "closed"
    with pytest.raises(BaseExceptionGroup):
        with held.scope():
            held.open(c.controls.bind(c.op))
    assert held.phase == "close-unconfirmed" and held.closed is None
    assert inspect(c).state == "quarantined"
    with pytest.raises(OwnershipConflict):
        close(c, held)
    assert c.channels[0].engine.calls == ["start", "stop"]


def test_clock_failure_cannot_skip_original_physical_cleanup(
    c: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = owner(c)

    def failed() -> datetime:
        raise OSError("controlled original bookkeeping clock failure")

    with pytest.raises(BaseExceptionGroup):
        with held.scope():
            held.open(c.controls.bind(c.op))
            monkeypatch.setattr(c.clock, "utcnow", failed)
    assert held.phase == "close-unconfirmed" and held.closed is None
    assert c.channels[0].capture.termination is not None
    assert c.channels[0].engine.calls == ["start", "stop"]


def test_cross_thread_owner_and_wrong_close_parent_are_refused(c: Case) -> None:
    held = owner(c)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(held.open, c.controls.bind(c.op)).result()
    assert not c.channels and held.phase == "new"
    with held.scope():
        held.open(c.controls.bind(c.op))
        wrong = c.op.cleanup(
            "wrong-close", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"parent_operation_id": "other-acquisition"})
        with pytest.raises(OwnershipConflict):
            held.close(wrong, c.controls.bind(wrong))
        assert inspect(c).state == "acquired"


@pytest.mark.parametrize("bad", [None, "", [], {}, True, 0])
def test_wrong_or_empty_owner_spec_fails_before_launch(c: Case, bad: Any) -> None:
    with pytest.raises(ValueError):
        RetainedSiteResource(
            bad,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
        )
    assert not c.channels
