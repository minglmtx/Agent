"""Registered site worker ownership and site readiness are separate facts.

Acquired means the original worker domain is fixed and persisted, before native
site startup. No caller receives a usable site until startup is verified too.
"""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract
from .slurm_binding import ScalarBatchBinding
from .worker_processes import CpuProcessStopFacts
from .site_worker import SiteWorkerConfiguration, SiteWorkerReady, SiteInstanceStarted
from .slurm_step import SlurmControllerStep, SlurmStepTarget
from .slurm_quiescence import SlurmUserQuiescence, SlurmUserRemoval
from .process_identity import ProcessIdentity
from .lifecycle import AllocationToken, OperationContext
from .evidence import EvidenceRef
from .state_scope import private_state_ref


class SiteSlurmBinding(ScalarBatchBinding):
    schema_version: Literal["site-slurm-binding/1"] = "site-slurm-binding/1"


class SiteResourceSpec(Contract):
    schema_version: Literal["site-resource-spec/1"] = "site-resource-spec/1"
    configuration: SiteWorkerConfiguration
    slurm: SiteSlurmBinding

    @model_validator(mode="after")
    def owner(self) -> Self:
        if self.token.owner.job_id != self.slurm.execution.job_id:
            raise ValueError("Site token changed original Slurm job")
        return self

    @property
    def token(self) -> AllocationToken:
        return self.configuration.token

    def check_operation(self, operation: OperationContext, mode: str) -> None:
        self.configuration.check_operation(operation, mode)


class SiteResourceReady(Contract):
    schema_version: Literal["site-resource-ready/1"] = "site-resource-ready/1"
    worker: SiteWorkerReady
    controller: SlurmControllerStep
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_domain(self) -> Self:
        target, guard = self.controller.target, self.worker.owner_guard
        if (
            target.resources != "cpu_only"
            or target.worker.writer != guard.worker
            or target.launcher == guard.supervisor
        ):
            raise ValueError("Site ready changed original guarded CPU domain")
        private_state_ref(self.evidence, "site-step-raw/1")
        return self


class SiteStepClosed(Contract):
    schema_version: Literal["site-step-closed/1"] = "site-step-closed/1"
    target: SlurmStepTarget
    quiescence: SlurmUserQuiescence | SlurmUserRemoval
    evidence: EvidenceRef

    @model_validator(mode="after")
    def original_domain(self) -> Self:
        if (
            self.target.resources != "cpu_only"
            or self.quiescence.original != self.target.worker
        ):
            raise ValueError("Site closure changed original CPU domain")
        private_state_ref(self.evidence, "site-step-raw/1")
        return self


class SiteProcessStop(CpuProcessStopFacts):
    schema_version: Literal["site-process-stop/1"] = "site-process-stop/1"


class SiteResourceAttempt(Contract):
    schema_version: Literal["site-resource-attempt/1"] = "site-resource-attempt/1"
    spawn_attempted: bool
    launcher: ProcessIdentity | None = None
    target: SlurmStepTarget | None = None
    ready: SiteResourceReady | None = None
    start_attempted: bool = False
    started: SiteInstanceStarted | None = None

    @model_validator(mode="after")
    def original_handles(self) -> Self:
        if not self.spawn_attempted and (
            self.launcher is not None
            or self.target is not None
            or self.ready is not None
            or self.start_attempted
            or self.started is not None
        ):
            raise ValueError("Unspawned site cannot claim acquired handles/effects")
        if self.target is not None and (
            self.target.launcher != self.launcher or self.target.resources != "cpu_only"
        ):
            raise ValueError("Site attempt changed original CPU launcher")
        if self.ready is not None and self.ready.controller.target != self.target:
            raise ValueError("Site ready differs from original target")
        if self.start_attempted and self.ready is None:
            raise ValueError("Site effects require original ready identity")
        if self.started is not None and not self.start_attempted:
            raise ValueError("Unstarted site cannot claim an endpoint")
        return self


class SiteResourceStarted(Contract):
    """Usable endpoint plus original ownership and persisted startup evidence."""

    schema_version: Literal["site-resource-started/1"] = "site-resource-started/1"
    ready: SiteResourceReady
    instance: SiteInstanceStarted
    evidence: EvidenceRef

    @model_validator(mode="after")
    def private_start(self) -> Self:
        private_state_ref(self.evidence, "site-resource-fact/1")
        return self
