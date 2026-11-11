"""Original terminal transport -> eligible independent DB requests, no DB dispatch yet."""

import json
from typing import Any
import pytest
from lab_generate_skill.domain.errors import EvidenceError, OperationStopped
from lab_generate_skill.sites.map.terminal_requests import reference_candidates
from map_registered_worker_fixtures import RegisteredMapCase
from map_terminal_fixtures import terminal
from map_terminal_request_fixtures import Requests, read_original, DerivedFiles, REGION
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("mode", ["native", "batch", "non200", "narrow"])
def test_actual_relay_complete_original_terminal_selection(
    mode: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = Requests(monkeypatch, mode)
    with terminal(registered_map, monkeypatch, before_capture=request) as c:
        evidence, files = read_original(c)
        calls = (
            len(request.calls),
            len(c.initial.browser.calls),
            len(c.original.case.commands.calls),
        )
        checked = files.evidence(evidence)
        for _ in range(2):
            result = reference_candidates(checked, guard(60))
            if mode in ("native", "batch"):
                assert len(result.selected) == 1 and result.skipped == ()
                row = result.selected[0]
                assert (
                    row.index == 0
                    and row.bounds == REGION
                    and row.body == request.delivered
                )
                assert row.response_kind == (
                    "adapted_union" if mode == "batch" else "native_200"
                )
                assert len(request.calls) == (3 if mode == "batch" else 1)
            else:
                assert result.selected == () and result.skipped == (
                    (
                        0,
                        (
                            "original_native_non200"
                            if mode == "non200"
                            else "original_reference_area_narrowed"
                        ),
                    ),
                )
        assert calls == (
            len(request.calls),
            len(c.initial.browser.calls),
            len(c.original.case.commands.calls),
        )


def test_original_cap_transport_mutations_cannot_yield_db_candidates(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = Requests(monkeypatch, "batch")
    with terminal(registered_map, monkeypatch, before_capture=request) as c:
        evidence, original = read_original(c)
        calls = (
            len(request.calls),
            len(c.initial.browser.calls),
            len(c.original.case.commands.calls),
        )
        mutations: tuple[tuple[str, str, Any], ...] = (
            ("request-0-browser-start.json", "plan_sha256", "f" * 64),
            (
                "request-0-browser-start.json",
                "actual_url",
                "http://127.0.0.1:1/api/0.6/map?bbox=0,0,0.1,0.1",
            ),
            ("request-0-browser-start.json", "last_unique_observation_sequence", 99),
            ("request-0-browser-start.json", "native_scope_or_cap_changed", True),
            (
                "request-0-browser-start.json",
                "original_absolute_monotonic_deadline",
                None,
            ),
            (
                "request-0-browser-start.json",
                "original_absolute_monotonic_deadline",
                True,
            ),
            (
                "request-0-browser-start.json",
                "original_absolute_monotonic_deadline",
                "300",
            ),
            (
                "request-0-browser-start.json",
                "original_absolute_monotonic_deadline",
                -1,
            ),
            ("request-0-browser-start.json", "native_request_budget_seconds", True),
            ("request-0-browser-start.json", "method", ""),
            ("request-0-browser-start.json", "actual_url", []),
            ("request-0-browser-end.json", "continue_returned", False),
            ("request-0-registration.json", "original_absolute_monotonic_deadline", 0),
            ("request-0-delivery-start.json", "adapted", False),
            ("request-0-delivery-start.json", "native_original_http200_claim", True),
            ("request-0-delivery-end.json", "delivery_complete", False),
            ("request-0-delivery-end.json", "errors", ["partial"]),
            ("request-0-delivery-end.json", "delivered_bytes", 0),
            ("request-0-delivery-end.json", "delivered_bytes", True),
            ("request-0-first-event-0000.json", "request_index", True),
            ("request-0-batch-event-0000.json", "event_index", 2048),
            ("request-0-batch-event-0000.json", "source_record", []),
        )
        for name, key, bad in mutations:
            data = object.__new__(DerivedFiles)
            data.original = original.original
            data.data = dict(original.data)
            data.change(name, **{key: bad})
            with pytest.raises((ValueError, EvidenceError), match="."):
                reference_candidates(data.evidence(evidence), guard(30))
        for missing in (
            "request-0-first-event-0001.json",
            "request-0-batch-event-0001.bin",
        ):
            data = object.__new__(DerivedFiles)
            data.original = original.original
            data.data = dict(original.data)
            del data.data[missing]
            with pytest.raises((ValueError, EvidenceError)):
                reference_candidates(data.evidence(evidence), guard(30))
        data = object.__new__(DerivedFiles)
        data.original = original.original
        data.data = dict(original.data)
        delivery = json.loads(data.data["request-0-delivery-start.json"])
        delivery["batch"]["native_children"] = 999
        data.change("request-0-delivery-start.json", **delivery)
        with pytest.raises(EvidenceError, match="recompute"):
            reference_candidates(data.evidence(evidence), guard(30))

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "terminal-selection")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(OperationStopped):
            reference_candidates(original.evidence(evidence), Cancel())
        assert calls == (
            len(request.calls),
            len(c.initial.browser.calls),
            len(c.original.case.commands.calls),
        )
