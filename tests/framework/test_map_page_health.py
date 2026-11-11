"""Current document health through original fixed capture and independent reader."""

from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.sites.map.page_capture import PAGE_HEALTH_PROGRAM
from lab_generate_skill.sites.map.page_health import MapPageHealth
from lab_generate_skill.sites.map.page_evidence import terminal_page_health
from lab_generate_skill.sites.map.browser_capture import MapBrowserCapture
from map_registered_worker_fixtures import RegisteredMapCase
from map_terminal_fixtures import terminal
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_map_browser_collection import capture
from preparation_record_fixtures import put
from test_slurm_commands import guard


def health(url: str = "http://map.local/directions") -> dict[str, Any]:
    return dict(
        url=url,
        sampled_url=url,
        title="OpenStreetMap",
        http_status=200,
        status_source="navigation_timing",
        login_page=False,
        error_page=False,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"http_status": True},
        {"http_status": 99},
        {"http_status": 600},
        {"http_status": "200"},
        {"http_status": None},
        {"status_source": "inferred"},
        {"status_source": "unavailable"},
        {"login_page": 0},
        {"title": None},
        {"url": ""},
        {"sampled_url": "other"},
        {"title": "x" * 65537},
        {"unexpected": True},
    ],
)
def test_health_rejects_incomplete_wrong_type_and_extreme(
    change: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        MapPageHealth.model_validate({**health(), **change})


@pytest.mark.parametrize(
    "mode",
    ["normal", "unavailable", "changed", "login", "error", "partial", "malformed"],
)
def test_fixed_health_capture_and_independent_closed_reader(
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    original = registered_map
    with terminal(original, monkeypatch) as c:
        b = c.initial.browser
        assert b.engine is not None and isinstance(
            b.engine.collector, MapBrowserCapture
        )
        collector = b.engine.collector
        assert b.collector is not None
        first = b.engine.last_readout
        count, calls = b.page.reads, list(b.calls)
        sample = health(b.page.url)
        if mode == "unavailable":
            sample.update(http_status=None, status_source="unavailable")
        if mode == "changed":
            sample.update(url=b.page.url + "#old", sampled_url=b.page.url + "#old")
        if mode == "login":
            b.page.url = sample["url"] = sample["sampled_url"] = (
                "http://map.local/login"
            )
        if mode == "error":
            sample["title"] = "Page Not Found | OpenStreetMap"
        reads: list[str] = []
        evaluate = b.page.evaluate

        def read(program: str, args: Any = None) -> Any:
            if program != PAGE_HEALTH_PROGRAM:
                return evaluate(program, args)
            reads.append(program)
            if mode == "partial":
                raise OSError("original passive health read acknowledgement lost")
            return [] if mode == "malformed" else sample

        monkeypatch.setattr(b.page, "evaluate", read)
        # Reject wrong ownership/version and pre-effect cancellation without a read.
        with pytest.raises(OwnershipConflict):
            collector.collect(object(), "map-page-health", "1", guard())
        with pytest.raises(OwnershipConflict):
            collector.collect(b.page, "map-page-health", "2", guard())
        with pytest.raises(OperationStopped):
            collector.collect(b.page, "map-page-health", "1", guard(-1))
        assert not reads and not collector.health.attempted
        recorder, request = capture(b, c.initial.session)
        request = request.model_copy(
            update={
                "collector_id": "map-page-health",
                "operation": request.operation.model_copy(
                    update={"operation_id": "terminal-health"}
                ),
            }
        )
        if mode in ("partial", "malformed"):
            from lab_generate_skill.adapters.browsergym.worker_client import (
                BrowserWorkerFailure,
            )

            with pytest.raises(BrowserWorkerFailure) as failure:
                recorder.capture(request, control=guard())
            assert failure.value.reply.error is not None
            assert failure.value.reply.error.type_name == (
                "OSError" if mode == "partial" else "ValidationError"
            )
            assert failure.value.reply.captured is None
            assert collector.health.attempted and b.engine.state == "closed"
            assert b.collector.state == "closed"
            assert (
                b.collector.native is not None
                and b.collector.native.requests.relay.physical_closed
            )
            with pytest.raises(InvalidTransition):
                collector.collect(b.page, "map-page-health", "1", guard())
            assert len(reads) == 1
            return
        result = recorder.capture(request, control=guard())
        assert recorder.intent_ref is not None
        intent_ref = recorder.intent_ref

        def independent() -> MapPageHealth:
            return terminal_page_health(
                c.load(), b.resource.evidence, intent_ref, result, guard(60)
            )

        fact = independent()
        assert fact.http_status == (None if mode in ("changed", "unavailable") else 200)
        assert fact.login_page == (mode == "login") and fact.error_page == (
            mode == "error"
        )
        assert (fact.sampled_url != fact.url) == (mode == "changed")
        assert (
            b.engine.last_readout is first
            and b.page.reads == count
            and b.calls == calls
        )
        assert len(reads) == 1 and b.collector.state == "published"
        with pytest.raises(InvalidTransition):
            collector.collect(b.page, "map-page-health", "1", guard())
        assert recorder.result is not None
        bad = recorder.result.model_copy(update={"request_sha256": "f" * 64})
        with pytest.raises(OwnershipConflict):
            terminal_page_health(
                c.load(),
                b.resource.evidence,
                recorder.intent_ref,
                put(b.resource.evidence, bad),
                guard(60),
            )
    assert original.worker is not None and original.worker.closed
    assert independent() == fact and len(reads) == 1
