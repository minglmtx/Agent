"""Shared original canonical initial capture reads and exact intent binding."""

import hashlib
from typing import TypeVar
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl

T = TypeVar("T", bound=Contract)


class MapInitialCaptureRecords:
    def __init__(self, store: EvidenceReader, evidence: MapInitialEvidence) -> None:
        self.store, self.evidence = store, MapInitialEvidence.model_validate(evidence)

    def _read(
        self, ref: EvidenceRef, schema: str, model: type[T], control: OperationControl
    ) -> T:
        private_state_ref(ref, schema)
        if ref.media_type != "application/json":
            raise ValueError("Original private Map capture JSON required")
        raw = self.store.read(ref, control=control)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (ref.size_bytes, ref.sha256):
            raise EvidenceIntegrityError("Original Map capture CAS bytes changed")
        result = model.model_validate_json(raw)
        if result.model_dump_json().encode() != raw:
            raise EvidenceIntegrityError("Noncanonical original Map capture record")
        control.checkpoint()
        return result

    def _capture(
        self,
        inputs: InitialObservationInputs,
        collector: tuple[str, str],
        control: OperationControl,
    ) -> tuple[BrowserCaptureIntent, BrowserCaptureResult]:
        config = inputs.browser.configuration
        intent = self._read(
            self.evidence.intent_ref,
            "browser-capture-intent/1",
            BrowserCaptureIntent,
            control,
        )
        result = self._read(
            self.evidence.result_ref,
            "browser-capture-result/1",
            BrowserCaptureResult,
            control,
        )
        request = intent.request
        returned = inputs.returned
        inputs.browser.check_operation(request.operation, "execute")
        request.check_readout(config.spec, returned)
        if (request.collector_id, request.collector_version) != collector or (
            intent.configuration_sha256
            != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
            or result.request_sha256 != request.digest
            or request.operation.operation_id
            in (
                returned.operation.operation_id,
                inputs.acquired.operation.operation_id,
                inputs.worker_acquired.operation.operation_id,
            )
            or result.captured_at < returned.observation.captured_at
        ):
            raise OwnershipConflict(
                "Map initial capture changed original operation/configuration/return"
            )
        return intent, result
