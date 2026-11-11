"""Read exact diagnostic bytes and separate original failure billing CAS facts."""

from lab_generate_skill.ports.lifecycle import OperationControl

import base64
from dataclasses import dataclass
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.model_request import ModelSendPlan
from lab_generate_skill.domain.model_failure import (
    ModelFailureFact,
    TransportDiagnostic,
)
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.adapters.processes.wire_json import json_object
from .provider_charge import exact_charge


@dataclass(frozen=True)
class FailureCharge:
    body: bytes
    provider_request_id: str
    charge: Money


class FailureEvidence:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def read(
        self, plan: ModelSendPlan, ref: EvidenceRef, control: OperationControl
    ) -> FailureCharge:
        ref = EvidenceRef.model_validate(ref)
        private_state_ref(ref, "model-transport-failure/1")
        if ref.size_bytes > plan.limits.max_response_bytes * 2 + 65536:
            raise ValueError("Diagnostic exceeds its frozen read bound")
        diagnostic = TransportDiagnostic.model_validate_json(
            self._store.read(ref, control=control)
        )
        if (
            diagnostic.request != plan.reservation.request
            or diagnostic.operation != plan.operation
        ):
            raise OwnershipConflict("Diagnostic is not the original request/operation")
        if not (
            (
                diagnostic.reason == "HTTP_STATUS"
                and diagnostic.status is not None
                and diagnostic.status >= 400
            )
            or (diagnostic.reason == "RESPONSE_PROTOCOL" and diagnostic.status == 200)
        ):
            raise ValueError(
                "Incomplete transport does not establish a complete failure bill"
            )
        raw = base64.b64decode(diagnostic.body_base64, validate=True)
        if len(raw) > plan.limits.max_response_bytes:
            raise ValueError("Original response exceeds frozen limit")
        body = json_object(raw, exact_numbers=True)
        if not isinstance(body.get("error"), dict) or not body["error"]:
            raise ValueError("Failure billing requires an explicit provider error")
        provider_id = body.get("id")
        usage = body.get("usage")
        charge = exact_charge(usage.get("cost") if isinstance(usage, dict) else None)
        if (
            not isinstance(provider_id, str)
            or not provider_id.strip()
            or charge is None
        ):
            raise ValueError("Failure request identity or exact charge remains unknown")
        return FailureCharge(raw, provider_id, charge)

    def response(
        self, plan: ModelSendPlan, data: bytes, control: OperationControl
    ) -> EvidenceRef:
        return self._store.put(
            data,
            EvidenceMetadata(
                media_type="application/octet-stream",
                content_schema=plan.reservation.request.role + "-model-response/1",
                visibility="private",
                producer="failure-billing-v1",
            ),
            control=control,
        )

    def publish(self, fact: ModelFailureFact, control: OperationControl) -> EvidenceRef:
        return self._store.put(
            fact.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="model-failure-billing/1",
                visibility="private",
                producer="failure-billing-v1",
            ),
            control=control,
        )
