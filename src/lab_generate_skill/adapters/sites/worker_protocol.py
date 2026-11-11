"""Canonical bounded site configure/start/close commands; never dynamic task scripts."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Identifier, Sha256
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_PACKET = 16 * 1024 * 1024
WORKER_MODULE = "lab_generate_skill.bootstrap.site_worker"
Phase = Literal["configure", "start", "task", "capture", "resume", "close"]


def valid_sequence(phase: Phase, sequence: int) -> bool:
    return (
        (phase == "configure" and sequence == 1)
        or (phase == "start" and sequence == 2)
        or (phase in ("task", "capture", "resume") and 3 <= sequence <= 10002)
        or (phase == "close" and 2 <= sequence <= 10003)
    )


class SiteWorkerCommand(Contract):
    schema_version: Literal["site-worker-command/8"] = "site-worker-command/8"
    session_id: Identifier
    sequence: int = Field(ge=1, le=10003)
    phase: Phase
    operation: OperationContext
    remaining_seconds: float = Field(gt=0, le=86400, allow_inf_nan=False)
    controller: ProcessIdentity | None = None
    configuration: SiteWorkerConfiguration | None = None

    task: SiteTaskRequest | None = None
    capture_request: SiteCaptureRequest | None = None
    capture_intent_ref: EvidenceRef | None = None
    resume: SiteResumeRequest | None = None
    resume_intent_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        first = self.phase == "configure"
        if (
            not valid_sequence(self.phase, self.sequence)
            or (self.task is not None) != (self.phase == "task")
            or (self.task is not None and self.task.operation != self.operation)
            or (self.capture_request is not None) != (self.phase == "capture")
            or (self.capture_intent_ref is not None) != (self.phase == "capture")
            or (
                self.capture_request is not None
                and self.capture_request.operation != self.operation
            )
            or (self.resume is not None) != (self.phase == "resume")
            or (self.resume_intent_ref is not None) != (self.phase == "resume")
            or (self.resume is not None and self.resume.operation != self.operation)
            or (self.controller is not None) != first
            or (self.configuration is not None) != first
            or self.operation.mode
            != (
                "cleanup"
                if self.phase in ("close", "resume")
                or (self.task is not None and self.task.action == "restore")
                else "execute"
            )
        ):
            raise ValueError("Configure precedes start; close may follow either once")
        if self.configuration is not None:
            self.configuration.check_operation(self.operation, "execute")
        if self.capture_intent_ref is not None:
            private_state_ref(self.capture_intent_ref, "site-capture-intent/2")
        if self.resume_intent_ref is not None:
            private_state_ref(self.resume_intent_ref, "site-resume-intent/1")
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Site command exceeds packet limit")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class SiteWorkerReply(Contract):
    schema_version: Literal["site-worker-reply/8"] = "site-worker-reply/8"
    session_id: Identifier
    sequence: int = Field(ge=1, le=10003)
    phase: Phase
    command_sha256: Sha256
    error: RemoteError | None = None
    started: SiteInstanceStarted | None = None
    exits: tuple[NativeServiceExit, ...] | None = None
    owner_guard: ProcessOwnerGuard | None = None
    installed_sources: InstalledReleaseSources | None = None
    task_result: SiteTaskResult | None = None
    capture_result: SiteTaskResult | None = None
    resume_result: SiteResumeResult | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if not valid_sequence(self.phase, self.sequence):
            raise ValueError("Site reply phase/sequence mismatch")
        if (self.owner_guard is None) != (self.installed_sources is None):
            raise ValueError("Site ownership/installation facts must be complete")
        if self.phase != "configure" and (
            self.owner_guard is not None or self.installed_sources is not None
        ):
            raise ValueError(
                "Only configure reports original identity and installation"
            )
        if self.phase != "start" and self.started is not None:
            raise ValueError("Only start reports a site endpoint")
        if self.phase != "task" and self.task_result is not None:
            raise ValueError("Only task reports a private task result")
        if self.phase != "capture" and self.capture_result is not None:
            raise ValueError("Only capture reports collector results")
        if self.phase != "resume" and self.resume_result is not None:
            raise ValueError("Only resume reports a private resume result")
        if self.error is None:
            if self.phase == "capture" and (
                self.capture_result is None or self.exits is not None
            ):
                raise ValueError(
                    "Capture requires original collector result and live instance"
                )
            if self.phase == "resume" and (
                self.resume_result is None or self.exits is not None
            ):
                raise ValueError(
                    "Resume requires actual result and original live instance"
                )
            if self.phase == "task" and (
                self.task_result is None or self.exits is not None
            ):
                raise ValueError(
                    "Task requires actual private result and a live instance"
                )
            if self.phase == "configure" and (
                self.owner_guard is None or self.exits is not None
            ):
                raise ValueError(
                    "Configure requires actual guarded installation and no site effects"
                )
            if self.phase == "start" and (
                self.started is None or self.exits is not None
            ):
                raise ValueError("Start requires the original actual endpoint")
            if self.phase == "close" and (
                self.exits is None or any(f.state != "reaped" for f in self.exits)
            ):
                raise ValueError("Successful close requires original launcher exits")
        else:
            validate_error_budget(self.error)
        if len(self.model_dump_json().encode()) > MAX_PACKET:
            raise ValueError("Site reply exceeds packet limit")
        return self


def decode_command(raw: bytes) -> SiteWorkerCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid site command bytes")
    json_object(raw)
    command = SiteWorkerCommand.model_validate_json(raw)
    if command.model_dump_json().encode() != raw:
        raise ValueError("Site command is not canonical")
    return command


def decode_reply(
    command: SiteWorkerCommand, configuration: SiteWorkerConfiguration, raw: bytes
) -> SiteWorkerReply:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PACKET:
        raise ValueError("Invalid site reply bytes")
    json_object(raw)
    reply = SiteWorkerReply.model_validate_json(raw)
    if reply.model_dump_json().encode() != raw:
        raise ValueError("Site reply is not canonical")
    if (reply.session_id, reply.sequence, reply.phase, reply.command_sha256) != (
        command.session_id,
        command.sequence,
        command.phase,
        command.digest,
    ):
        raise ValueError("Site reply changed original command")
    if reply.task_result is not None and (
        command.task is None or reply.task_result.request_sha256 != command.task.digest
    ):
        raise ValueError("Site task result changed original request")
    if reply.capture_result is not None and (
        command.capture_request is None
        or reply.capture_result.request_sha256 != command.capture_request.digest
    ):
        raise ValueError("Site capture result changed original request")
    if reply.resume_result is not None and (
        command.resume is None
        or reply.resume_result.request_sha256 != command.resume.digest
    ):
        raise ValueError("Site resume result changed original request")
    if reply.started is not None and reply.started.files != configuration.files:
        raise ValueError("Site reply changed original files/instance")
    if reply.owner_guard is not None:
        assert reply.installed_sources is not None
        actual, expected = reply.installed_sources, configuration.installation
        if reply.owner_guard.controller != command.controller or (
            actual.release_id,
            actual.manifest_sha256,
            actual.executable,
        ) != (
            expected.manifest.release_id,
            expected.manifest_ref.sha256,
            expected.python_executable,
        ):
            raise ValueError("Site reply changed original guard/installation")
        if WORKER_MODULE not in {m.name for m in actual.modules}:
            raise ValueError("Fixed site module missing from installation")
    return reply
