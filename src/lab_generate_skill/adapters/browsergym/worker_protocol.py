"""Bounded canonical browser commands and retained facts, never launch permission.

First start fixes session/spec/installation/asset paths and original controller.
Every command consumes a sequence; the final slot is reserved for close. Replies
bind the exact command and original operation; errors may retain obtained facts.
"""

import hashlib
from lab_generate_skill.domain import browser_worker
from typing import Any, Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    viewport_reference,
)
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import (
    InstalledReleaseSources,
)
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_PACKET = 16 * 1024 * 1024
MAX_COMMANDS = 10000
WORKER_MODULE = "lab_generate_skill.bootstrap.browser_worker"
Phase = Literal["configure", "start", "step", "capture", "close"]


class BrowserWorkerCommand(Contract):
    schema_version: Literal["browser-worker-command/3"] = "browser-worker-command/3"
    session_id: Identifier
    sequence: int = Field(ge=1, le=MAX_COMMANDS)
    phase: Phase
    operation: OperationContext
    remaining_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    controller: ProcessIdentity | None = None
    configuration: browser_worker.BrowserWorkerConfiguration | None = None
    action: BrowserAction | None = None
    capture_request: BrowserCaptureRequest | None = None
    capture_intent_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        first = self.phase == "configure"
        if (
            (self.sequence == 1) != first
            or (self.controller is not None) != first
            or (self.configuration is not None) != first
        ):
            raise ValueError("Only sequence one configures the original worker")
        if self.phase == "start" and self.sequence != 2:
            raise ValueError("Native initialization requires sequence two")
        if self.phase in ("step", "capture") and self.sequence < 3:
            raise ValueError("Browser operation precedes native initialization")
        if (self.action is not None) != (self.phase == "step"):
            raise ValueError("Only step carries the exact browser action")
        if (self.capture_request is not None) != (self.phase == "capture") or (
            self.capture_intent_ref is not None
        ) != (self.phase == "capture"):
            raise ValueError("Capture requires exactly one request and durable intent")
        if (
            self.capture_request is not None
            and self.capture_request.operation != self.operation
        ):
            raise ValueError("Capture changed original operation")
        if self.capture_intent_ref is not None:
            private_state_ref(self.capture_intent_ref, "browser-capture-intent/1")
        if self.operation.mode != ("cleanup" if self.phase == "close" else "execute"):
            raise ValueError("Browser command changed operation phase")
        if self.sequence == MAX_COMMANDS and self.phase != "close":
            raise ValueError("Final sequence is reserved for close")
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Browser command exceeds packet budget")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class BrowserWorkerReply(Contract):
    schema_version: Literal["browser-worker-reply/3", "browser-worker-reply/4"] = (
        "browser-worker-reply/3"
    )
    session_id: Identifier
    sequence: int = Field(ge=1, le=MAX_COMMANDS)
    phase: Phase
    command_sha256: Sha256
    error: RemoteError | None = None
    readout: BrowserReadout | None = None
    captured: BrowserCaptureResult | None = None
    viewport: ObservationViewport | None = None
    owner_guard: ProcessOwnerGuard | None = None
    installed_sources: InstalledReleaseSources | None = None

    @model_serializer(mode="wrap")
    def versioned_output(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version == "browser-worker-reply/3":
            result.pop("viewport", None)
        return result

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.schema_version == "browser-worker-reply/3":
            if self.viewport is not None or (
                self.readout is not None
                and viewport_reference(self.readout.observation) is not None
            ):
                raise ValueError(
                    "Legacy reply cannot carry an unbound viewport artifact"
                )
        else:
            if (
                self.viewport is None
                or self.readout is None
                or self.phase not in ("start", "step")
            ):
                raise ValueError(
                    "Viewport reply requires its same-capture readout and complete public body"
                )
            self.viewport.require_observation(self.readout.observation)
        if (self.owner_guard is None) != (self.installed_sources is None):
            raise ValueError("Observed start facts must be complete")
        if self.phase != "configure" and self.owner_guard is not None:
            raise ValueError("Only configure returns installation and owner facts")
        if self.phase != "capture" and self.captured is not None:
            raise ValueError("Only capture returns private collector facts")
        if self.error is None:
            if (self.captured is not None) != (self.phase == "capture"):
                raise ValueError("Successful capture requires its original result")
            if (self.readout is not None) != (self.phase in ("start", "step")):
                raise ValueError("Successful start/step requires actual readout")
            if (self.owner_guard is not None) != (self.phase == "configure"):
                raise ValueError(
                    "Successful start requires actual source and owner facts"
                )
        elif self.error is not None:
            validate_error_budget(self.error)
        if self.phase in ("configure", "close", "capture") and self.readout is not None:
            raise ValueError("Close cannot present a previous action as its return")
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Browser reply exceeds packet budget")
        return self


def decode_command(raw: bytes) -> BrowserWorkerCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid browser command bytes")
    json_object(raw)
    result = BrowserWorkerCommand.model_validate_json(raw)
    if result.model_dump_json().encode() != raw:
        raise ValueError("Browser command must be canonical")
    return result


def decode_reply(
    command: BrowserWorkerCommand, spec: BrowserSessionSpec, raw: bytes
) -> BrowserWorkerReply:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid browser reply bytes")
    json_object(raw)
    result = BrowserWorkerReply.model_validate_json(raw)
    if result.model_dump_json().encode() != raw:
        raise ValueError("Browser reply must be canonical")
    if (result.session_id, result.sequence, result.phase, result.command_sha256) != (
        command.session_id,
        command.sequence,
        command.phase,
        command.digest,
    ):
        raise ValueError("Browser reply changed original command")
    if result.readout is not None and (
        result.readout.scope,
        result.readout.operation,
        result.readout.action,
    ) != (spec.scope, command.operation, command.action):
        raise ValueError("Browser returned foreign scope/action/operation")
    if result.captured is not None and (
        command.capture_request is None
        or result.captured.request_sha256 != command.capture_request.digest
    ):
        raise ValueError("Browser capture returned a foreign request")
    if result.owner_guard is not None:
        assert (
            command.configuration is not None and result.installed_sources is not None
        )
        expected = command.configuration.installation
        actual = result.installed_sources
        if result.owner_guard.controller != command.controller or (
            actual.release_id,
            actual.manifest_sha256,
            actual.executable,
        ) != (
            expected.manifest.release_id,
            expected.manifest_ref.sha256,
            expected.python_executable,
        ):
            raise ValueError("Browser owner/installation differs from frozen start")
        if WORKER_MODULE not in {m.name for m in actual.modules}:
            raise ValueError("Fixed browser entry missing from observed installation")
    return result
