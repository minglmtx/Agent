"""Bind complete terminal files to the original prepared browser and capture."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from lab_generate_skill.domain.map_terminal_evidence import MapTerminalSelection
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.map_published_files import MapPublishedFiles
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_bounds import Bounds
from .terminal_files import TerminalFiles, private_bytes, private_record
from .state_rules import object_json
from .tasks.overlay_spec import NativeOverlaySpec
from .tasks.overlay_policy import overlay_initial_spec
from .tasks.overlay_reference_policy import original_reference_bounds, CONTRACT_SHA


@dataclass(frozen=True)
class TerminalMapEvidence:
    selection: MapTerminalSelection
    initial: InitialObservationInputs
    intent: BrowserCaptureIntent
    result: BrowserCaptureResult
    publication: MapBrowserPublication
    readout: BrowserReadout
    files: TerminalFiles
    original_bounds: Bounds
    pages: tuple[dict[str, Any], ...]


def terminal_evidence(
    selection: MapTerminalSelection,
    initial: InitialObservationInputs,
    store: EvidenceReader,
    published: MapPublishedFiles,
    control: OperationControl,
) -> TerminalMapEvidence:
    selection = MapTerminalSelection.model_validate(selection)
    initial = InitialObservationInputs.model_validate(initial)
    cfg = initial.browser.configuration
    chosen = cfg.initialization
    if (
        selection.initial != initial.selection
        or not isinstance(chosen, MapNativeInitialization)
        or cfg.map_inputs is None
    ):
        raise OwnershipConflict(
            "Original explicit prepared Map terminal selection required"
        )
    chosen.check(cfg.spec)
    if (
        chosen.prepared_ref != selection.initial.preparation.prepared_ref
        or initial.spec != overlay_initial_spec(initial.prepared.scope.task)
    ):
        raise OwnershipConflict("Map terminal changed original preparation/coverage")
    private = private_record(
        store,
        initial.prepared.private_checks_ref,
        "map-native-overlay/1",
        NativeOverlaySpec,
        control,
    )
    if (
        private.task != initial.prepared.scope.task
        or private.native_contract_ref.sha256 != CONTRACT_SHA
    ):
        raise OwnershipConflict(
            "Map terminal changed original selected native contract"
        )
    private_bytes(store, private.native_contract_ref, "map-native-contract/1", control)
    bounds = original_reference_bounds(store, selection.original_reference_ref, control)
    intent = private_record(
        store,
        selection.capture_intent_ref,
        "browser-capture-intent/1",
        BrowserCaptureIntent,
        control,
    )
    result = private_record(
        store,
        selection.capture_result_ref,
        "browser-capture-result/1",
        BrowserCaptureResult,
        control,
    )
    request = intent.request
    initial.browser.check_operation(request.operation, "execute")
    if (
        (request.collector_id, request.collector_version) != ("map-native-process", "1")
        or intent.configuration_sha256
        != hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
    ):
        raise OwnershipConflict(
            "Map terminal changed original collector/configuration/intent"
        )
    publication = MapBrowserPublication.model_validate_json(result.private_result)
    if (
        publication.model_dump_json() != result.private_result
        or publication.plan != cfg.map_inputs.plan
        or publication.collection_sha256 != cfg.map_inputs.collection.digest
        or cfg.map_inputs.collection.operation != initial.returned.operation
    ):
        raise OwnershipConflict(
            "Map terminal publication changed original plan/collection"
        )
    files = TerminalFiles(publication, published, control)
    raw = files.read(publication.terminal_readout.path, control)
    readout = BrowserReadout.model_validate_json(raw)
    request.check_readout(cfg.spec, readout)
    initial.browser.check_operation(readout.operation, "execute")
    if (
        readout.model_dump_json().encode() != raw
        or (publication.sequence, publication.observation_sha256)
        != (readout.observation.sequence, request.observation_sha256)
        or result.captured_at < readout.observation.captured_at
        or request.operation.operation_id
        in (
            readout.operation.operation_id,
            initial.returned.operation.operation_id,
            initial.acquired.operation.operation_id,
            initial.worker_acquired.operation.operation_id,
        )
    ):
        raise OwnershipConflict(
            "Map terminal capture changed its unique original return"
        )
    if publication.sequence == 0 and readout != initial.returned:
        raise OwnershipConflict("Map terminal replaced the original initial readout")
    closed = object_json(files.read("map-process-close.json", control))
    finished = object_json(files.read("map-existing-pending-finish.json", control))
    count = closed.get("request_count")
    if (
        type(count) is not int
        or not 0 <= count <= cfg.map_inputs.collection.max_requests
        or closed.get("original_relay_physical_closed") is not True
        or type(closed.get("unique_readout_count")) is not int
        or closed.get("unique_readout_count") != publication.sequence + 1
        or closed.get("process_errors") != []
        or closed.get("cleanup_errors") != []
        or closed.get("task_success_or_admission_claim") is not False
    ):
        raise EvidenceIntegrityError("Map terminal collection did not close completely")
    if any(
        finished.get(k) is not v
        for k, v in (
            ("new_requests_created", False),
            ("new_observation_created", False),
            ("original_deadlines_extended", False),
            ("passed", True),
        )
    ) or finished != {
        "schema_version": "map-existing-native-pending-settle/1",
        "request_ids": [f"request-{i}" for i in range(count)],
        "new_requests_created": False,
        "new_observation_created": False,
        "original_deadlines_extended": False,
        "passed": True,
    }:
        raise EvidenceIntegrityError(
            "Map terminal did not settle the exact original requests"
        )
    pages = []
    expected = []
    for sequence in range(publication.sequence + 1):
        binding = object_json(files.read(f"map-observation-{sequence}.json", control))
        returned = BrowserReadout.model_validate_json(
            json.dumps(binding.get("readout"))
        )
        initial.browser.check_operation(returned.operation, "execute")
        if (
            binding.get("schema_version") != "map-native-observation-binding/1"
            or binding.get("plan_sha256") != publication.plan.digest
            or returned.scope != publication.plan.scope
            or returned.observation.sequence != sequence
            or (sequence == 0 and returned != initial.returned)
            or (sequence == publication.sequence and returned != readout)
        ):
            raise OwnershipConflict(
                "Map terminal lost its continuous original readouts"
            )
        seen = binding.get("request_ids_seen")
        if (
            type(seen) is not list
            or seen != [f"request-{i}" for i in range(len(seen))]
            or len(seen) > count
        ):
            raise EvidenceIntegrityError("Map readout changed original request prefix")
        name = f"map-page-{sequence}-unique_return.json"
        pages.append(_page(files, name, returned, "unique_return", control))
        expected.append(files.members[name])
    # Every explicit capture retains post-settle facts against the same last
    # unique return, including protocol/environment terminal actions.
    name = f"map-page-{publication.sequence}-terminal.json"
    pages.append(_page(files, name, readout, "terminal", control))
    expected.append(files.members[name])
    page_close = object_json(files.read("map-page-close.json", control))
    records = tuple(
        ReleaseFile.model_validate_json(json.dumps(v))
        for v in page_close.get("complete_records", [])
    )
    if (
        page_close.get("schema_version") != "map-original-native-page-close/1"
        or page_close.get("plan_sha256") != publication.plan.digest
        or type(page_close.get("unique_return_count")) is not int
        or page_close.get("unique_return_count") != publication.sequence + 1
        or page_close.get("terminal_attempted") is not True
        or page_close.get("pending_record_retained") is not False
        or page_close.get("errors") != []
        or records != tuple(expected)
    ):
        raise EvidenceIntegrityError("Map terminal surface collection is incomplete")
    return TerminalMapEvidence(
        selection,
        initial,
        intent,
        result,
        publication,
        readout,
        files,
        bounds,
        tuple(pages),
    )


def _page(
    files: TerminalFiles,
    name: str,
    readout: BrowserReadout,
    phase: str,
    control: OperationControl,
) -> dict[str, Any]:
    value = object_json(files.read(name, control))
    if (
        (
            value.get("schema_version"),
            value.get("plan_sha256"),
            value.get("phase"),
            value.get("unique_observation_sequence"),
            value.get("original_readout"),
        )
        != (
            "map-original-native-page-facts/1",
            files.publication.plan.digest,
            phase,
            readout.observation.sequence,
            readout.model_dump(mode="json"),
        )
        or value.get("new_action_or_observation") is not False
        or value.get("semantic_success_or_admission_claim") is not False
        or type(value.get("facts")) is not dict
    ):
        raise EvidenceIntegrityError(
            "Original terminal page facts lost their original readout"
        )
    return value
