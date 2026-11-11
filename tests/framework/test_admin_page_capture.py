"""Fixed Admin predicates and browser leaf state/identity boundaries."""

from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.shopping_admin.page_capture import (
    AdminPageHealthCollector,
)
from lab_generate_skill.sites.shopping_admin.evidence_schema import AdminPageHealth
from browser_worker_fixtures import case
from browsergym_fixtures import operation, LoopbackAuthority
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "terminal",
        "scope",
        "observation",
        "collector",
        "version",
        "native",
        "bad_bool",
        "missing",
        "cancel_after_read",
    ],
)
def test_original_engine_capture_is_read_only_and_once(fault: str) -> None:
    _, service, _, client = case()
    initial = client.start(operation(client.spec, "start"), control=guard())
    calls: list[str] = []

    class Control:
        def checkpoint(self) -> float:
            if fault == "cancel_after_read" and calls:
                raise OperationStopped("CANCELLED", "capture")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    class Page:
        def evaluate(self, script: str) -> dict[str, Any]:
            calls.append(script)
            if fault == "native":
                raise OSError("original page unavailable")
            return dict(
                schema_version="admin-page-health/1",
                url=client.spec.task.start_url,
                login="false" if fault == "bad_bool" else False,
                page_error=False,
            )

    engine = BrowserGymEngine(
        client.spec,
        LoopbackAuthority(),
        SystemClock(),
        NavigatePublicTask(),
        collector=None if fault == "missing" else AdminPageHealthCollector(),
    )
    engine.state = "terminal" if fault == "terminal" else "ready"
    engine.last_readout = initial
    engine.env = SimpleNamespace(page=Page())
    req = BrowserCaptureRequest(
        scope=client.spec.scope,
        operation=operation(client.spec, "capture"),
        observation_sha256=hashlib.sha256(
            initial.observation.model_dump_json().encode()
        ).hexdigest(),
        collector_id="foreign" if fault == "collector" else "admin-page-health",
        collector_version="2" if fault == "version" else "1",
    )
    if fault == "scope":
        req = req.model_copy(
            update={"scope": req.scope.model_copy(update={"context_id": "foreign"})}
        )
    if fault == "observation":
        req = req.model_copy(update={"observation_sha256": "f" * 64})
    if fault in ("none", "terminal"):
        result = engine.capture_page(req, control=guard())
        assert AdminPageHealth.model_validate_json(result.private_result).login is False
        assert engine.state == ("terminal" if fault == "terminal" else "ready")
        assert result.request_sha256 == req.digest
        with pytest.raises(InvalidTransition):
            engine.capture_page(req, control=guard())
        assert len(calls) == 1
    else:
        with pytest.raises(
            (
                ValueError,
                OSError,
                InvalidTransition,
                OwnershipConflict,
                OperationStopped,
            )
        ):
            engine.capture_page(req, control=Control())
        assert len(calls) == (
            1 if fault in ("native", "bad_bool", "cancel_after_read") else 0
        )
        if fault not in ("scope", "observation", "missing"):
            assert getattr(engine, "state") == "quarantined"
        if fault == "cancel_after_read":
            assert (
                engine.last_capture is not None
                and engine.last_capture.request_sha256 == req.digest
            )
            with pytest.raises(InvalidTransition):
                engine.capture_page(req, control=guard())
            assert len(calls) == 1
    assert (
        engine.last_readout == initial
        and engine.sequence == 0
        and not engine.events.events
    )
    service.close()


def test_capture_domain_rejects_invalid_scope_and_time() -> None:
    from lab_generate_skill.domain.browser_capture import BrowserCaptureResult

    with pytest.raises(ValueError):
        BrowserCaptureResult(
            request_sha256="a" * 64, captured_at=datetime.now(), private_result="{}"
        )
    with pytest.raises(ValueError):
        BrowserCaptureResult(
            request_sha256="a" * 64,
            captured_at=datetime.now(timezone.utc),
            private_result="中" * 100000,
        )
