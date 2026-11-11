"""Bounded private transport diagnostics; no credentials or exception messages."""

from lab_generate_skill.ports.lifecycle import OperationControl

import base64
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ResolvedModelRequest
from lab_generate_skill.domain.model_failure import TransportDiagnostic
from lab_generate_skill.ports.evidence import EvidenceStore


def preserve_transport_failure(
    store: EvidenceStore,
    request: ResolvedModelRequest,
    op: OperationContext,
    reason: str,
    status: int | None,
    body: bytes,
    error_types: tuple[str, ...],
    control: OperationControl,
) -> EvidenceRef:
    payload = TransportDiagnostic(
        request=request.request,
        operation=op,
        reason=reason,
        status=status,
        body_base64=base64.b64encode(body).decode("ascii"),
        error_types=error_types,
    )
    return store.put(
        payload.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="model-transport-failure/1",
            visibility="private",
            producer="openrouter-http-v1",
        ),
        control=control,
    )
