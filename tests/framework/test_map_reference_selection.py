"""Original terminal/inspection -> private selection; no DB capture authority."""

import json
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.map_reference_selection import MapReferenceSelection
from lab_generate_skill.sites.map.reference_selection import (
    select_reference,
    read_reference_selection,
    verify_reference_selection,
)
from map_terminal_fixtures import terminal
from map_terminal_request_fixtures import Requests, read_original
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("mode", ["native", "batch"])
def test_original_terminal_to_selected_cas_same_inspection_no_query(
    mode: str,
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = Requests(monkeypatch, mode)
    with terminal(registered_map, monkeypatch, before_capture=requests) as c:
        raw, files = read_original(c)
        evidence = files.evidence(raw)
        store = c.original.resource.evidence
        inspection = c.original.request("inspect")
        calls = (
            len(requests.calls),
            len(c.original.case.commands.calls),
            len(c.initial.browser.calls),
        )
        selected = select_reference(
            c.reference, evidence, inspection, 0, store, guard(60)
        )
        reference = put(store, selected)
        assert (
            read_reference_selection(store, reference, inspection, guard()) == selected
        )
        verify_reference_selection(selected, evidence, inspection, store, guard(60))
        assert (
            select_reference(c.reference, evidence, inspection, 0, store, guard(60))
            == selected
        )
        other = selected.model_copy(update={"inspection_sha256": "f" * 64})
        assert other.original_request_key == selected.original_request_key
        assert selected.original_request_key == (evidence.publication.plan.digest, 0)
        assert calls == (
            len(requests.calls),
            len(c.original.case.commands.calls),
            len(c.initial.browser.calls),
        )


@pytest.mark.parametrize("mode", ["none", "non200", "narrow"])
def test_absent_or_ineligible_original_request_never_creates_selection(
    mode: str,
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = None if mode == "none" else Requests(monkeypatch, mode)
    with terminal(registered_map, monkeypatch, before_capture=request) as c:
        raw, files = read_original(c)
        calls = (len(c.original.case.commands.calls), len(c.initial.browser.calls))
        with pytest.raises(ValueError, match="not eligible"):
            select_reference(
                c.reference,
                files.evidence(raw),
                c.original.request("inspect"),
                0,
                c.original.resource.evidence,
                guard(60),
            )
        assert calls == (
            len(c.original.case.commands.calls),
            len(c.initial.browser.calls),
        )


def test_selection_wrong_identity_full_response_region_types_and_cancel(
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = Requests(monkeypatch, "native")
    with terminal(registered_map, monkeypatch, before_capture=requests) as c:
        raw, files = read_original(c)
        evidence = files.evidence(raw)
        store = c.original.resource.evidence
        inspection = c.original.request("inspect")
        selected = select_reference(
            c.reference, evidence, inspection, 0, store, guard(60)
        )
        ref = put(store, selected)
        assert inspection.snapshot_ref is not None
        calls = (
            len(requests.calls),
            len(c.original.case.commands.calls),
            len(c.initial.browser.calls),
        )
        update: dict[str, Any]
        for update in (
            {"inspection_sha256": "f" * 64},
            {"bounds": ("-74.01", "40.75", "-73.96", "40.79")},
            {"bounds": (selected.bounds[0] + "0", *selected.bounds[1:])},
        ):
            bad = MapReferenceSelection.model_validate(
                selected.model_copy(update=update)
            )
            with pytest.raises((ValueError, OwnershipConflict)):
                read_reference_selection(store, put(store, bad), inspection, guard())
        # Parent verification recomputes the original full-file response. Worker
        # declaration checks do not impersonate browser-file authority.
        for update in (
            {"records_sha256": "f" * 64},
            {"response_kind": "adapted_union"},
            {"payload": selected.payload.model_copy(update={"sha256": "f" * 64})},
            {
                "terminal_handle": selected.terminal_handle.model_copy(
                    update={"plan_sha256": "f" * 64}
                )
            },
            {
                "request_index": 1,
                "payload": selected.payload.model_copy(
                    update={"path": "request-1-response.bin"}
                ),
            },
        ):
            bad = MapReferenceSelection.model_validate(
                selected.model_copy(update=update)
            )
            with pytest.raises((ValueError, EvidenceError)):
                verify_reference_selection(bad, evidence, inspection, store, guard(60))
        for update in (
            {
                "snapshot_ref": inspection.snapshot_ref.model_copy(
                    update={"sha256": "f" * 64}
                )
            },
            {
                "binding_ref": inspection.binding_ref.model_copy(
                    update={"sha256": "f" * 64}
                )
            },
            {
                "operation": inspection.operation.model_copy(
                    update={"attempt_id": "other"}
                )
            },
            {
                "operation": inspection.operation.model_copy(
                    update={
                        "operation_id": c.initial.preparation.request.operation.operation_id
                    }
                )
            },
            {"action": "prepare"},
        ):
            with pytest.raises((ValueError, OwnershipConflict)):
                read_reference_selection(
                    store, ref, inspection.model_copy(update=update), guard()
                )
        invalid: tuple[dict[str, Any], ...] = (
            {"request_index": True},
            {"request_index": -1},
            {"request_index": 256},
            {"request_index": "0"},
            {"request_index": None},
            {"bounds": []},
            {"bounds": ""},
            {"bounds": [0, 1, 2, 3]},
            {"bounds": ["", "1", "2", "3"]},
            {"bounds": ["1" * 257, "1", "2", "3"]},
            {"terminal_selection_ref": None},
            {"records_sha256": ""},
            {"schema_version": "map-reference-selection/0"},
            {"extra": 1},
            {"payload": {**selected.payload.model_dump(), "path": "other.bin"}},
            {"payload": {**selected.payload.model_dump(), "executable": True}},
            {"payload": {**selected.payload.model_dump(), "size_bytes": 0}},
        )
        for update in invalid:
            with pytest.raises(ValidationError):
                MapReferenceSelection.model_validate_json(
                    json.dumps({**selected.model_dump(mode="json"), **update})
                )
        bad_indexes: tuple[Any, ...] = (True, -1, 256, "0", None)
        for bad_index in bad_indexes:
            with pytest.raises(ValueError, match="request index"):
                select_reference(
                    c.reference, evidence, inspection, bad_index, store, guard()
                )
        invalid_records: tuple[Any, ...] = (None, [], {}, "", 0)
        for bad_record in invalid_records:
            with pytest.raises(ValidationError):
                MapReferenceSelection.model_validate(bad_record)

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "map-reference-selection")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(OperationStopped):
            read_reference_selection(store, ref, inspection, Cancel())
        assert calls == (
            len(requests.calls),
            len(c.original.case.commands.calls),
            len(c.initial.browser.calls),
        )
