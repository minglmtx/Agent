"""Actual managed-store/controller gates, no source retag, claim or website grant."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from closed_source_read_fixtures import actual_read_case
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


@pytest.mark.parametrize(
    "fault", ["none", "revoke", "after", "cancel", "thread", "quarantine", "nested"]
)
def test_actual_current_storage_gates_have_no_graph_or_permission_cache(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = actual_read_case(tmp_path, installed_sources, fresh_cas=True)
    # Historical source material remains foreign. Only the current review
    # controller's own metadata admission is tested by check_current here.
    with pytest.raises(OwnershipConflict):
        c.transport.require_current(c.material, c.op)
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    calls = 0
    original = c.current.admission.authorize_storage

    def authorize(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        original(*args, **kwargs)
        if fault == "after" and calls == 1:
            c.current.admission.stop_new_io()

    def no_child(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Same-call current storage gate must not reread a graph")

    monkeypatch.setattr(c.current.admission, "authorize_storage", authorize)
    monkeypatch.setattr(c.transport.runner, "run", no_child)
    control = c.controls.bind(c.op)
    if fault == "none":
        c.transport.check_current(control)
        c.transport.check_current(control)
        assert calls == 4
    elif fault in ("revoke", "after"):
        if fault == "revoke":
            c.current.admission.stop_new_io()
        with pytest.raises(InvalidTransition):
            c.transport.check_current(control)
        assert calls == (1 if fault == "revoke" else 2)
    elif fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", c.op.operation_id)

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(OperationStopped):
            c.transport.check_current(Cancelled())
        assert calls == 0
    elif fault == "thread":
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(c.transport.check_current, control).result()
        assert calls == 0
    elif fault == "quarantine":
        c.transport.quarantined = True
        with pytest.raises(ClosedSourceReadFailure):
            c.transport.check_current(control)
        assert calls == 0
    else:
        with c.current.store.read_scope(control):
            with pytest.raises(InvalidTransition):
                c.transport.check_current(control)
        assert calls == 0
    assert c.current.store.state == "ready"
    assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == before
    assert c.transport.last_capture is None and c.transport.timings == []
    # Exception/cancellation releases the original lock, with no new session.
    with c.current.store.read_scope(c.controls.bind(c.op)):
        pass
