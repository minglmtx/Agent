"""Original private terminal readback, with no new browser or DB work."""

from datetime import timedelta
from pathlib import Path
import json
from typing import Any
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.map.tasks.overlay_reference_policy import (
    full_original_bbox_retained,
    original_reference_bounds,
)
from lab_generate_skill.sites.map.native_surface_script import COMBINED_READ
from map_initial_records_fixtures import InitialCase
from map_terminal_fixtures import terminal, PROOF
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("action", ["none", "click", "protocol"])
def test_original_terminal_complete_members_and_continuous_readouts_without_effects(
    action: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with terminal(registered_map, monkeypatch, action=action) as c:
        b = c.initial.browser
        calls = (list(b.calls), len(registered_map.case.commands.calls), b.page.reads)
        value = c.load()
        assert value.readout == b.engine.last_readout if b.engine is not None else False
        assert value.readout.observation.sequence == (0 if action == "none" else 1)
        assert value.readout.protocol_terminal == (action == "protocol")
        assert value.publication.sequence == value.readout.observation.sequence
        assert len(value.pages) == value.publication.sequence + 2
        assert value.pages[-1]["phase"] == "terminal"
        assert value.original_bounds == (
            "-74.01369094848634",
            "40.74784218528665",
            "-73.95532608032228",
            "40.79106937427438",
        )
        assert c.load().readout == value.readout
        assert calls == (b.calls, len(registered_map.case.commands.calls), b.page.reads)


@pytest.mark.parametrize(
    "fault",
    [
        "configuration",
        "request",
        "selector",
        "capture-time",
        "plan",
        "sequence",
        "readout-pin",
        "missing",
        "corrupt",
        "permission",
        "proof",
        "wrong-attempt",
    ],
)
def test_terminal_binding_or_full_file_failure_never_returns_candidate(
    fault: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with terminal(registered_map, monkeypatch) as c:
        store = c.original.resource.evidence
        selection = c.selection
        intent = BrowserCaptureIntent.model_validate_json(
            store.read(selection.capture_intent_ref)
        )
        result = BrowserCaptureResult.model_validate_json(
            store.read(selection.capture_result_ref)
        )
        publication = MapBrowserPublication.model_validate_json(result.private_result)
        if fault == "configuration":
            intent = intent.model_copy(update={"configuration_sha256": "f" * 64})
        if fault == "request":
            result = result.model_copy(update={"request_sha256": "f" * 64})
        if fault == "selector":
            intent = intent.model_copy(
                update={
                    "request": intent.request.model_copy(
                        update={"collector_id": "map-initial-readiness"}
                    )
                }
            )
            result = result.model_copy(update={"request_sha256": intent.request.digest})
        if fault == "capture-time":
            result = result.model_copy(
                update={"captured_at": c.initial.result.captured_at - timedelta(days=1)}
            )
        if fault == "plan":
            publication = publication.model_copy(
                update={
                    "plan": publication.plan.model_copy(
                        update={"artifact_id": "foreign"}
                    )
                }
            )
        if fault == "sequence":
            publication = publication.model_copy(update={"sequence": 1})
        if fault == "readout-pin":
            publication = publication.model_copy(
                update={
                    "terminal_readout": publication.terminal_readout.model_copy(
                        update={"sha256": "f" * 64}
                    )
                }
            )
        if fault in ("plan", "sequence", "readout-pin"):
            result = result.model_copy(
                update={"private_result": publication.model_dump_json()}
            )
        selection = selection.model_copy(
            update={
                "capture_intent_ref": put(store, intent),
                "capture_result_ref": put(store, result),
            }
        )
        if fault in ("missing", "corrupt"):
            manifest = json.loads(
                (
                    Path(publication.plan.private_root) / "published/manifest.json"
                ).read_bytes()
            )
            path = Path(manifest["artifact"]["root"]) / "map-terminal-readout.json"
            if fault == "missing":
                path.parent.chmod(0o700)
                path.unlink()
            else:
                path.chmod(0o600)
                path.write_bytes(b"changed")
        if fault == "permission":
            c.initial.browser.member_change["user_inode"] = 1
        if fault == "proof":
            selection = selection.model_copy(
                update={
                    "original_reference_ref": c.original.put(
                        b"{}", "map-native-layer-proof/1"
                    )
                }
            )
        if fault == "wrong-attempt":
            c.operation = c.operation.model_copy(update={"attempt_id": "foreign"})
        calls = (list(c.initial.browser.calls), len(registered_map.case.commands.calls))
        try:
            with pytest.raises(
                (ValueError, EvidenceError, OwnershipConflict, FileNotFoundError)
            ):
                c.load(selection)
        finally:
            c.initial.browser.member_change.clear()
        assert calls == (
            c.initial.browser.calls,
            len(registered_map.case.commands.calls),
        )


def test_original_reference_region_not_historical_admission(
    registered_map: RegisteredMapCase,
) -> None:
    c = registered_map
    ref = c.put(PROOF.read_bytes(), "map-native-layer-proof/1")
    bounds = original_reference_bounds(c.resource.evidence, ref, guard())
    assert full_original_bbox_retained(bounds, bounds)
    assert full_original_bbox_retained(("-74.02", "40.74", "-73.95", "40.8"), bounds)
    assert not full_original_bbox_retained(
        ("-74.01", "40.75", "-73.96", "40.79"), bounds
    )
    for bad in (None, False, [], [0, 0, 1, 1], ["NaN", "0", "1", "1"]):
        assert not full_original_bbox_retained(bad, bounds)

    class Cancel:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "terminal")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        original_reference_bounds(c.resource.evidence, ref, Cancel())


@pytest.mark.parametrize(
    "value",
    [None, False, 0, "", [], {}, {"schema_version": "map-terminal-selection/0"}],
)
def test_original_terminal_selection_invalid_input(value: object) -> None:
    with pytest.raises(ValueError):
        MapTerminalSelection.model_validate(value)


def test_protocol_terminal_selection_reads_post_settle_surface(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    settled = {"surface": {"after_original_pending": True}, "route": {}}

    def after_return(initial: InitialCase) -> None:
        page = initial.browser.page
        original = page.evaluate

        def evaluate(expression: str, args: Any = None) -> Any:
            if expression == COMBINED_READ:
                return settled
            return original(expression, args)

        monkeypatch.setattr(page, "evaluate", evaluate)

    with terminal(
        registered_map, monkeypatch, action="protocol", before_capture=after_return
    ) as c:
        value = c.load()
        assert value.readout.protocol_terminal
        assert value.pages[-2]["phase"] == "unique_return"
        assert value.pages[-2]["facts"] != settled
        assert value.pages[-1]["phase"] == "terminal"
        assert value.pages[-1]["facts"] == settled
        assert value.pages[-1]["original_readout"] == value.readout.model_dump(
            mode="json"
        )
        assert value.pages[-1]["new_action_or_observation"] is False
