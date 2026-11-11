"""Supervised one-POST OpenRouter transport; auth stays on the private stdin pipe.

Only exact production endpoint or explicit loopback test mode is accepted. No
environment credentials, implicit retry, redirects or automatic model fallback.
Parent process owns durable budget permits; worker never receives those permits.
"""

from lab_generate_skill.adapters.processes.deadline import DeadlineControl

import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import (
    ResolvedModelRequest,
    check_model_operation,
)
from lab_generate_skill.domain.model_response import (
    ProviderReply,
    ModelTransportFailure,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from .http_evidence import preserve_transport_failure
from .openrouter_request import prepare_openrouter
from .openrouter_response import decode_openrouter
from .http_packet import parse_packet, retained_command_failure


class OpenRouterTransport:
    def __init__(
        self,
        credential: str,
        evidence: EvidenceStore,
        controls: OperationControls,
        *,
        endpoint: str = "https://openrouter.ai/api/v1/chat/completions",
        test_loopback: bool = False,
    ) -> None:
        if (
            type(credential) is not str
            or not credential
            or len(credential) > 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in credential)
        ):
            raise ValueError("Invalid memory credential")
        if type(test_loopback) is not bool or type(endpoint) is not str:
            raise ValueError("Invalid endpoint configuration")
        parsed = urlsplit(endpoint)
        if test_loopback:
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "::1"}
                or not parsed.port
            ):
                raise ValueError("Test endpoint must be an explicit loopback HTTP port")
        elif endpoint != "https://openrouter.ai/api/v1/chat/completions":
            raise ValueError("Production endpoint must be the fixed OpenRouter API")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path != "/api/v1/chat/completions"
        ):
            raise ValueError("Endpoint cannot contain credentials or routing overrides")
        self._credential, self._endpoint = credential, endpoint
        self._store, self._controls = evidence, controls

    def validate(self, request: ResolvedModelRequest, op: OperationContext) -> None:
        request, op = ResolvedModelRequest.model_validate(
            request
        ), OperationContext.model_validate(op)
        check_model_operation(request.request, op)
        if op.mode != "execute":
            raise ValueError("Cleanup cannot send HTTP requests")
        self._controls.bind(op).checkpoint()
        prepare_openrouter(request)

    def send(
        self, request: ResolvedModelRequest, op: OperationContext
    ) -> ProviderReply:
        request, op = ResolvedModelRequest.model_validate(
            request
        ), OperationContext.model_validate(op)
        self.validate(request, op)
        control = self._controls.bind(op)
        payload = prepare_openrouter(request)
        spec = json.dumps(
            {
                "endpoint": self._endpoint,
                "credential": self._credential,
                "body_base64": base64.b64encode(payload).decode("ascii"),
                "max_response_bytes": request.limits.max_response_bytes,
                "timeout": control.checkpoint(),
            },
            separators=(",", ":"),
        ).encode()
        argv = (
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("http_worker.py")),
        )
        status: int | None = None
        body = b""
        reason = "PROCESS"
        error_types: tuple[str, ...] = ()
        try:
            capture = ProcessRunner(
                max_output_bytes=(request.limits.max_response_bytes * 4 + 2) // 3
                + 65536
            ).run(argv, control, stdin_bytes=spec)
            if capture.returncode != 0 or capture.stderr:
                raise ValueError("HTTP worker failed")
            reason = "WORKER_PROTOCOL"
            status, body, complete, error_types = parse_packet(
                capture.stdout, request.limits.max_response_bytes
            )
            reason = "HTTP_IO"
            if not complete or error_types:
                raise ValueError("HTTP worker did not complete and close cleanly")
            reason = "HTTP_STATUS"
            if status != 200:
                raise ValueError("HTTP response was not successful")
            reason = "RESPONSE_PROTOCOL"
            return decode_openrouter(request, body)
        except BaseException as error:
            command_error = retained_command_failure(error)
            if command_error is not None:
                reason = command_error.reason_code
                try:
                    status, body, _, error_types = parse_packet(
                        command_error.capture.stdout, request.limits.max_response_bytes
                    )
                except (ValueError, TypeError):
                    pass
            error_types = error_types or (type(error).__name__,)
            try:
                ref = preserve_transport_failure(
                    self._store,
                    request,
                    op,
                    reason,
                    status,
                    body,
                    error_types,
                    control=DeadlineControl(5, "evidence-diagnostic"),
                )
            except BaseException as storage_error:
                raise BaseExceptionGroup(
                    "Transport and diagnostic persistence failed",
                    [error, storage_error],
                ) from None
            raise ModelTransportFailure(reason, ref) from error
