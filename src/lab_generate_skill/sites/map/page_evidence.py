"""Independent original health intent/result reader; never queries the browser."""

import hashlib
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_evidence import TerminalMapEvidence
from .terminal_files import private_record
from .page_health import MapPageHealth


def terminal_page_health(
    terminal: TerminalMapEvidence,
    store: EvidenceReader,
    intent_ref: EvidenceRef,
    result_ref: EvidenceRef,
    control: OperationControl,
) -> MapPageHealth:
    intent = private_record(
        store, intent_ref, "browser-capture-intent/1", BrowserCaptureIntent, control
    )
    result = private_record(
        store, result_ref, "browser-capture-result/1", BrowserCaptureResult, control
    )
    cfg = terminal.initial.browser.configuration
    req = intent.request
    terminal.initial.browser.check_operation(req.operation, "execute")
    req.check_readout(cfg.spec, terminal.readout)
    if (
        (req.collector_id, req.collector_version) != ("map-page-health", "1")
        or intent.configuration_sha256
        != hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != req.digest
        or result.captured_at < terminal.result.captured_at
        or req.operation.operation_id
        in (
            terminal.intent.request.operation.operation_id,
            terminal.readout.operation.operation_id,
            terminal.initial.returned.operation.operation_id,
        )
    ):
        raise OwnershipConflict(
            "Map health must follow same original terminal publication"
        )
    fact = MapPageHealth.model_validate_json(result.private_result)
    if fact.model_dump_json() != result.private_result:
        raise EvidenceIntegrityError(
            "Original complete Map health record is not canonical"
        )
    control.checkpoint()
    return fact
