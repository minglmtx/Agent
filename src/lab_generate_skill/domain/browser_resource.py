"""Attempt-bound browser resource declaration and observed startup facts.

The existing ResourceJournal owns registration/acquisition. These records bind
that allocation to its frozen worker; neither a record nor a reaped leader is
permission or proof of complete browser-resource restoration.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .browser_worker import BrowserWorkerConfiguration
from .browser import observation_reference
from .evidence import EvidenceRef
from .state_scope import private_state_ref
from .lifecycle import AllocationToken, OperationContext
from .process_guard import ProcessOwnerGuard
from .release_installation import InstalledReleaseSources
from .errors import OwnershipConflict
from .browser_step import BrowserSlurmBinding, BrowserStepStarted
from .slurm_step import SlurmStepTarget
from .process_identity import ProcessIdentity


class BrowserResourceSpec(Contract):
    schema_version: Literal["browser-resource-spec/4"] = "browser-resource-spec/4"
    token: AllocationToken
    configuration: BrowserWorkerConfiguration
    slurm: BrowserSlurmBinding

    @model_validator(mode="after")
    def binding(self) -> Self:
        token = self.token
        scope = self.configuration.spec.scope
        if (
            token.scope,
            token.resource_kind,
            token.provider_id,
            token.provider_version,
        ) != ("attempt", "browser", "fixed-browser-worker", "3"):
            raise ValueError("Browser requires its explicit attempt provider")
        if (token.owner, token.attempt_id) != (scope.owner, scope.attempt_id):
            raise ValueError("Browser worker changed original resource scope")
        if token.owner.job_id != self.slurm.execution.job_id:
            raise ValueError("Browser owner differs from original Slurm execution")
        if self.configuration.map_inputs is not None and (
            self.configuration.map_inputs.plan.token != token
        ):
            raise ValueError("Map browser files changed original resource token")
        return self

    def check_operation(self, operation: OperationContext, mode: str) -> None:
        token = self.token
        if operation.mode != mode or (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (
            token.owner.run_id,
            token.owner.owner_id,
            token.attempt_id,
            token.allocation_id,
            token.recovery_ref,
        ):
            raise OwnershipConflict(
                "Browser operation must retain original allocation and recovery"
            )


class BrowserResourcePrepared(Contract):
    """Original worker identity before browser creation; no readiness claim."""

    schema_version: Literal["browser-resource-prepared/1"] = (
        "browser-resource-prepared/1"
    )
    owner_guard: ProcessOwnerGuard
    step: BrowserStepStarted
    installed_sources: InstalledReleaseSources

    @model_validator(mode="after")
    def original_worker(self) -> Self:
        target = self.step.controller.target
        if (
            target.worker.writer != self.owner_guard.worker
            or target.launcher == self.owner_guard.supervisor
        ):
            raise ValueError("Prepared browser differs from original guarded worker")
        return self


class BrowserResourceStarted(Contract):
    schema_version: Literal["browser-resource-started/2"] = "browser-resource-started/2"
    owner_guard: ProcessOwnerGuard
    step: BrowserStepStarted
    installed_sources: InstalledReleaseSources
    initial_observation_ref: EvidenceRef
    initial_return_ref: EvidenceRef

    @model_validator(mode="after")
    def references(self) -> Self:
        target = self.step.controller.target
        if (
            target.worker.writer != self.owner_guard.worker
            or target.launcher == self.owner_guard.supervisor
        ):
            raise ValueError("Browser step differs from original guarded worker")
        observation_reference(self.initial_observation_ref)
        private_state_ref(self.initial_return_ref, "browser-initial-return/1")
        return self


class BrowserResourceAttempt(Contract):
    schema_version: Literal["browser-resource-attempt/3"] = "browser-resource-attempt/3"
    start_attempted: bool
    launcher_pid: int | None = Field(default=None, ge=1)
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    owner_guard: ProcessOwnerGuard | None = None
    prepared: BrowserResourcePrepared | None = None
    prepared_ref: EvidenceRef | None = None
    started: BrowserResourceStarted | None = None

    @model_validator(mode="after")
    def original_handles(self) -> Self:
        if not self.start_attempted and any(
            x is not None
            for x in (
                self.launcher_pid,
                self.launcher,
                self.target,
                self.owner_guard,
                self.prepared,
                self.prepared_ref,
                self.started,
            )
        ):
            raise ValueError("Unattempted browser cannot claim process handles")
        if self.launcher is not None and self.launcher.process_id != self.launcher_pid:
            raise ValueError("Browser cleanup changed original launcher PID")
        if self.target is not None and (
            self.target.launcher != self.launcher or self.target.resources != "cpu_only"
        ):
            raise ValueError("Browser cleanup changed original CPU target")
        if self.owner_guard is not None and (
            self.target is None or self.target.worker.writer != self.owner_guard.worker
        ):
            raise ValueError("Browser guard is not bound to original observed target")
        if (
            self.started is not None
            and self.started.step.controller.target != self.target
        ):
            raise ValueError("Started browser changed original step target")
        if self.started is not None and self.started.owner_guard != self.owner_guard:
            raise ValueError("Started browser differs from retained original guard")
        if self.prepared_ref is not None:
            private_state_ref(self.prepared_ref, "browser-resource-prepared/1")
            if self.prepared is None:
                raise ValueError("Prepared reference lacks original observed facts")
        if self.prepared is not None and (
            self.prepared.step.controller.target != self.target
            or self.prepared.owner_guard != self.owner_guard
        ):
            raise ValueError("Prepared browser changed original target or guard")
        if self.started is not None and (
            self.prepared is None
            or self.prepared_ref is None
            or self.started.step != self.prepared.step
            or self.started.installed_sources != self.prepared.installed_sources
        ):
            raise ValueError("Initialized browser lacks original prepared identity")
        return self
