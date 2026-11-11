"""Independent original site process admission with mandatory source permission.

Use at registered_site's existing authority port. Source/release/claim, native
task intent and residual file disposition remain the supplied authority's job.
This class never grants those rights, starts or stops workers, or retries a
request. It owns only independent original kernel handles until final closure.
Use its context scope around registered_site: observation handles must close even
when failed bookkeeping skips the authority callback. This is not another site
owner, runner or closure grant. Inspection requires existing outer supervision.
"""

import os
import threading
from typing import Literal
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from . import step


class ObservedSiteResourceAuthority:
    def __init__(
        self,
        spec: SiteResourceSpec,
        acquisition: OperationContext,
        *,
        source: SiteResourceAuthority,
        evidence: EvidenceStore,
    ) -> None:
        self.spec = SiteResourceSpec.model_validate(spec)
        self.acquisition = OperationContext.model_validate(acquisition)
        self.spec.check_operation(self.acquisition, "execute")
        if self.acquisition.parent_operation_id is not None:
            raise OwnershipConflict("Original independent site acquisition required")
        if source is None or evidence is None:
            raise ValueError("Original source authority and evidence are mandatory")
        self.source, self.evidence = source, evidence
        self._context = (os.getpid(), threading.get_ident())
        self._spawn_attempted = self._authorized = self._start_attempted = False
        self._close_attempted = False
        self._configure_attempted = self._started = False
        self._active = self._scope_used = False
        self._state = step.SiteStepState()
        self._ready: SiteResourceReady | None = None
        self._closed: SiteStepClosed | None = None
        self._observations: list[EvidenceRef] = []
        self._raw = WorkerStepEvidence("site")

    def __enter__(self) -> "ObservedSiteResourceAuthority":
        if self._context != (os.getpid(), threading.get_ident()) or self._scope_used:
            raise OwnershipConflict("Original site authority scope cannot be replayed")
        self._scope_used = self._active = True
        return self

    def __exit__(
        self, error_type: object, primary: BaseException | None, traceback: object
    ) -> None:
        if self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Foreign caller cannot release site observations")
        self._active = False
        self._release_observation_handles(primary)

    def _release_observation_handles(self, primary: BaseException | None) -> None:
        errors: list[BaseException] = []
        for name in ("processes", "pin"):
            held = getattr(self._state, name)
            setattr(self._state, name, None)
            if held is not None:
                try:
                    held.close()
                except BaseException as error:
                    errors.append(error)
        if errors:
            combined = BaseExceptionGroup(
                "Original site verification and handle cleanup failed",
                ([primary] if primary is not None else []) + errors,
            )
            if self._closed is not None:
                setattr(combined, "site_step_evidence_ref", self._closed.evidence)
            raise combined from None

    @property
    def observations(self) -> tuple[EvidenceRef, ...]:
        return tuple(self._observations)

    @property
    def ready(self) -> SiteResourceReady | None:
        return self._ready

    @property
    def closed(self) -> SiteStepClosed | None:
        """Independent physical fact only; source permission is checked separately."""
        return self._closed

    def _owner(self, control: OperationControl) -> None:
        if not self._active:
            raise OwnershipConflict("Original site authority admission scope inactive")
        if self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Site authority escaped original caller context")
        control.checkpoint()
        if current_process_identity() != self.spec.slurm.parent.writer:
            raise OwnershipConflict("Site authority changed original Slurm writer")
        step.check_parent(self.spec, self.spec.slurm.parent.writer, control)
        control.checkpoint()

    def _owned_scope(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        *,
        cleanup: bool = False,
    ) -> None:
        if SiteResourceSpec.model_validate(spec) != self.spec:
            raise OwnershipConflict("Site authority changed original resource")
        operation = OperationContext.model_validate(operation)
        self.spec.check_operation(operation, "cleanup" if cleanup else "execute")
        if (not cleanup and operation != self.acquisition) or (
            cleanup
            and (
                operation.parent_operation_id != self.acquisition.operation_id
                or operation.cancellation_ref is not None
            )
        ):
            raise OwnershipConflict("Site authority changed original operation")
        if self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Site authority escaped original caller context")
        if not self._active:
            raise OwnershipConflict("Original site authority admission scope inactive")

    def _scope(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
        *,
        cleanup: bool = False,
    ) -> None:
        self._owned_scope(spec, operation, cleanup=cleanup)
        self._owner(control)

    def authorize_spawn(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope(spec, operation, control)
        if self._spawn_attempted:
            raise OwnershipConflict("Original site admission cannot be replayed")
        self._spawn_attempted = True
        self.source.authorize_spawn(spec, operation, control)
        self._scope(spec, operation, control)
        self._authorized = True

    def verify(
        self,
        configuration: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if configuration != self.spec.configuration or phase not in (
            "configure",
            "start",
            "close",
        ):
            raise OwnershipConflict("Site command changed frozen configuration/phase")
        self._scope(self.spec, operation, control, cleanup=phase == "close")
        if not self._authorized or self._close_attempted:
            raise OwnershipConflict("Site command lacks original live admission")
        if phase == "configure":
            if self._configure_attempted:
                raise OwnershipConflict("Original site configure is one-shot")
            self._configure_attempted = True
        if phase == "start":
            if self._ready is None or self._start_attempted:
                raise OwnershipConflict("Original ready site start is one-shot")
            self._start_attempted = True
        self.source.verify(configuration, phase, operation, control)
        self._scope(self.spec, operation, control, cleanup=phase == "close")

    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope(spec, operation, control)
        ready = SiteResourceReady.model_validate(ready)
        if (
            not self._authorized
            or self._state.target is not None
            or self._close_attempted
        ):
            raise OwnershipConflict("No new original site observation is permitted")
        target = ready.controller.target
        self._raw.require(self.evidence, ready.evidence, target, "ready", control)
        self._state.launcher = target.launcher
        observed = step.observe_ready(
            spec, self._state, ready.worker, self.evidence, control
        )
        self._observations.append(observed.evidence)
        if observed.controller != ready.controller:
            raise OwnershipConflict("Independent original site controller differs")
        self.source.verify_ready(spec, ready, operation, control)
        self._scope(spec, operation, control)
        self._ready = ready

    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope(spec, operation, control)
        started = SiteInstanceStarted.model_validate(started)
        if (
            not self._start_attempted
            or self._close_attempted
            or ready != self._ready
            or started.files != self.spec.configuration.files
        ):
            raise OwnershipConflict("Site startup changed original ready allocation")
        self.source.verify_started(spec, ready, started, operation, control)
        self._scope(spec, operation, control)
        self._started = True

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        if configuration != self.spec.configuration:
            raise OwnershipConflict("Task changed original site configuration")
        request = SiteTaskRequest.model_validate(request)
        request.check_site(configuration)
        self._owner(control)
        if self._ready is None or not self._started or self._close_attempted:
            raise OwnershipConflict("Task requires original active site admission")
        self.source.verify_task(configuration, request, control)
        self._owner(control)

    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        supplied: SiteStepClosed | None,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        # Wrong-scope callers cannot release another owner's retained handles.
        self._owned_scope(spec, operation, cleanup=True)
        if self._close_attempted:
            raise OwnershipConflict("Original site close admission is one-shot")
        self._close_attempted = True
        primary: BaseException | None = None
        try:
            self._owner(control)
            attempt = SiteResourceAttempt.model_validate(attempt)
            if (
                not self._authorized
                or self._state.target is None
                or self._state.launcher is None
                or attempt.target != self._state.target
                or attempt.launcher != self._state.launcher
                or not attempt.spawn_attempted
                or termination is None
                or termination.state != "reaped"
                or termination.process_id != self._state.launcher.process_id
                or termination.cleanup_errors
            ):
                raise OwnershipConflict("No independently held original site target")
            if supplied is None:
                raise OwnershipConflict(
                    "Original site target is held but durable closure evidence is unavailable"
                )
            if supplied.target != self._state.target:
                raise OwnershipConflict("Site closure evidence changed original target")
            self._raw.require(
                self.evidence, supplied.evidence, supplied.target, "closed", control
            )
            observed = step.observe_closed(
                spec,
                self._state,
                termination,
                self.evidence,
                control,
                metadata_control=control,
            )
            if observed is None or observed.target != supplied.target:
                raise OwnershipConflict("Original complete site closure not observed")
            self._closed = observed
            self._observations.append(observed.evidence)
            receipt = ClosureReceipt.model_validate(
                self.source.verify_closed(
                    spec, attempt, termination, supplied, operation, control
                )
            )
            if (
                receipt.token != spec.token
                or receipt.operation_id != operation.operation_id
                or receipt.status != "closed"
                or receipt.primary_error is not None
            ):
                raise OwnershipConflict("Original source/native closure unconfirmed")
            for reference in receipt.evidence:
                if reference.visibility != "private":
                    raise OwnershipConflict("Original site closure must remain private")
                self.evidence.read(reference, control=control)
            self._scope(spec, operation, control, cleanup=True)
            return receipt.model_copy(
                update={
                    "evidence": tuple(
                        dict.fromkeys((*receipt.evidence, observed.evidence))
                    )
                }
            )
        except BaseException as error:
            primary = error
            if self._closed is not None:
                setattr(error, "site_step_evidence_ref", self._closed.evidence)
            raise
        finally:
            self._release_observation_handles(primary)
