"""Recheck complete actual script bodies and original renderer proof, without HTTP."""

from collections.abc import Mapping
import hashlib
from urllib.parse import urlsplit
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_evidence import TerminalMapEvidence
from .state_rules import object_json
from .native_served_rules import reviewed_sources, candidate_names, matched_sources


def reviewed_frontend_served(
    terminal: TerminalMapEvidence,
    originals: Mapping[str, bytes],
    control: OperationControl,
) -> bool:
    inputs = terminal.initial.browser.configuration.map_inputs
    if inputs is None:
        raise EvidenceIntegrityError("Original Map browser inputs missing")
    expectation = reviewed_sources(originals, inputs.collection.tile_origin)
    files = terminal.files
    if not any(
        p["facts"]["surface"].get("map_visible") is True for p in terminal.pages
    ):
        return False
    value = object_json(files.read("map-actually-served.json", control))
    closed = object_json(files.read("map-served-close.json", control))
    expected_pins = {
        n: hashlib.sha256(s.encode()).hexdigest() for n, s in expectation.sources
    }
    if (
        value.get("schema_version") != "map-original-actually-served/1"
        or value.get("plan_sha256") != terminal.publication.plan.digest
        or value.get("passed") is not True
        or value.get("expected_sources") != [n for n, _ in expectation.sources]
        or value.get("original_source_pins")
        != {n: hashlib.sha256(s).hexdigest() for n, s in originals.items()}
        or value.get("expected_source_pins") != expected_pins
        or value.get("private_tile_origin") != inputs.collection.tile_origin
        or value.get("actual_renderer_functions")
        != dict(expectation.renderer_functions)
        or any(
            value.get(k) is not False
            for k in (
                "source_only_claim",
                "task_admission_claim",
                "new_requests_or_observations",
            )
        )
    ):
        raise EvidenceIntegrityError(
            "Original actually served source/renderer binding differs"
        )
    original_readouts = [
        p["original_readout"]
        for p in terminal.pages
        if p["facts"]["surface"].get("map_visible") is True
    ]
    if value.get("original_readout") != original_readouts[0]:
        raise EvidenceIntegrityError(
            "Actually served proof lost first visible original return"
        )
    rows = value.get("responses")
    if type(rows) is not list or not 1 <= len(rows) <= 256:
        raise EvidenceIntegrityError("Original complete served responses missing")
    origin = urlsplit(terminal.initial.prepared.public_task.start_url)
    found: set[str] = set()
    for index, row in enumerate(rows):
        if type(row) is not dict or type(row.get("actual_url")) is not str:
            raise EvidenceIntegrityError("Malformed original script response")
        url = urlsplit(row["actual_url"])
        pin = ReleaseFile.model_validate(row.get("body"))
        body = files.pinned(pin, control)
        actual = matched_sources(expectation, body)
        required = candidate_names(row["actual_url"])
        if (
            (url.scheme, url.netloc) != (origin.scheme, origin.netloc)
            or url.fragment
            or url.username is not None
            or url.password is not None
            or type(row.get("http_status")) is not int
            or row["http_status"] != 200
            or row.get("resource_type") != "script"
            or row.get("original_main_frame") is not True
            or row.get("from_service_worker") is not False
            or not required
            or row.get("required_sources") != list(required)
            or row.get("full_reviewed_executable_sources_present") != list(actual)
            or not set(required) <= set(actual)
            or pin.path != f"map-served-{index}.js"
        ):
            raise EvidenceIntegrityError("Original complete script response differs")
        found.update(actual)
    if (
        found != set(expected_pins)
        or value.get("matched_sources") != sorted(found)
        or closed
        != {
            "plan_sha256": terminal.publication.plan.digest,
            "final_state": "verified",
            "responses_seen": len(rows),
            "pending_body_retained": False,
            "errors": [],
            "cleanup_errors": [],
            "task_success_or_admission_claim": False,
        }
    ):
        raise EvidenceIntegrityError(
            "Original served collection incomplete or not closed"
        )
    control.checkpoint()
    return True
