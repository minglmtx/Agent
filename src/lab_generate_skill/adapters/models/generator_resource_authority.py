"""Actual local resource verification within an explicitly pinned launch scope.

The caller must be trusted bootstrap: a supplied spec is NOT user permission.
Compose with RunGeneratorResourceAuthority and per-request admission. This
implementation independently checks files, allocation and original step facts;
it never submits, retries, signals, takes over, or defaults to an allow callback.
Use only with registered_generator's mandatory model/config preflight and
installed-worker handshake. Do not duplicate multi-GB model hashing here.
Synchronous verification needs the separately required outer hard supervisor.
"""

import os
import threading
from pathlib import Path

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import (
    GeneratorStepStarted,
    GeneratorStepCleanup,
    GeneratorStepClosed,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.step_launch import generator_step_name
from lab_generate_skill.adapters.releases.documents import EvidenceReleaseDocuments
from .generator_launch_files import verify_launch_files, verify_system_command
from .generator_resource_records import phase, check_operation
from .generator_authority_evidence import require_step_raw
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree, pin_user_tree
from .generator_step import (
    GeneratorStepState,
    same_allocation,
    observe_started,
    observe_closed,
    retain_step_failure,
)


class PinnedSlurmGeneratorAuthority:
    def __init__(
        self,
        spec: GeneratorResourceSpec,
        startup: OperationContext,
        *,
        workspace_root: Path,
        evidence: EvidenceStore,
        allocation_verifier: SlurmAllocationVerifier,
    ) -> None:
        self._spec = GeneratorResourceSpec.model_validate(spec)
        self._startup = OperationContext.model_validate(startup)
        check_operation(self._spec, self._startup, "execute")
        if self._startup.parent_operation_id is not None:
            raise OwnershipConflict(
                "Pinned launch requires an independent start operation"
            )
        self._root, self._evidence, self._verifier = (
            workspace_root,
            evidence,
            allocation_verifier,
        )
        self._context = (os.getpid(), threading.get_ident())
        self._pin: PinnedUserTree | None = None
        self._authorized = False
        self._state = GeneratorStepState()
        self._started: GeneratorStepStarted | None = None
        self._closed: GeneratorStepClosed | None = None
        self._observations: list[EvidenceRef] = []

    @property
    def started(self) -> GeneratorStepStarted | None:
        return self._started

    @property
    def closed(self) -> GeneratorStepClosed | None:
        return self._closed

    @property
    def observations(self) -> tuple[EvidenceRef, ...]:
        """Persisted observation identities for bootstrap audit, never permits."""
        return tuple(self._observations)

    def _scope(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        control: OperationControl,
        *,
        cleanup: bool = False,
    ) -> None:
        self._owned_scope(spec, op, cleanup=cleanup)
        control.checkpoint()
        if current_process_identity() != spec.slurm.allocation.facts.writer:
            raise OwnershipConflict("Actual caller is not the original Slurm writer")
        control.checkpoint()

    def _owned_scope(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        *,
        cleanup: bool = False,
    ) -> None:
        spec, op = GeneratorResourceSpec.model_validate(
            spec
        ), OperationContext.model_validate(op)
        if self._context != (os.getpid(), threading.get_ident()) or spec != self._spec:
            raise OwnershipConflict(
                "Resource authority escaped its fixed execution scope"
            )
        check_operation(spec, op, "cleanup" if cleanup else "execute")
        if (not cleanup and op != self._startup) or (
            cleanup and op.parent_operation_id != self._startup.operation_id
        ):
            raise OwnershipConflict(
                "Resource authority operation differs from original start"
            )

    def authorize_start(
        self,
        spec: GeneratorResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope(spec, op, control)
        manifest = EvidenceReleaseDocuments(self._evidence).manifest(
            spec.release_ref, control
        )
        verify_launch_files(manifest, self._root, spec.python_executable, control)
        for executable in (spec.slurm.srun_executable, spec.slurm.scontrol_executable):
            verify_system_command(executable, control)
        original = spec.slurm.allocation
        actual = self._verifier.observe(
            original.facts.execution,
            original.facts.writer,
            phase(op, "authority-allocation"),
        )
        try:
            same_allocation(original, actual)
            self._scope(spec, op, control)
        except BaseException as error:
            setattr(error, "generator_step_evidence_ref", actual.evidence)
            raise
        self._observations.append(actual.evidence)
        self._authorized = True

    def verify_started(
        self,
        spec: GeneratorResourceSpec,
        started: GeneratorStepStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope(spec, op, control)
        if not self._authorized or self._closed is not None:
            raise OwnershipConflict("Worker has no current original start admission")
        started = GeneratorStepStarted.model_validate(started)
        same_allocation(spec.slurm.allocation, started.allocation)
        target = started.controller.target
        if (
            target.step_name != generator_step_name(spec.token)
            or target.execution != spec.slurm.allocation.facts.execution
        ):
            raise OwnershipConflict("Worker belongs to another original step")
        if self._state.target is not None and self._state.target != target:
            raise OwnershipConflict("Original authority target cannot change")
        require_step_raw(self._evidence, started.evidence, target, "started", control)
        self._state.start_attempted = True
        self._state.launcher = target.launcher
        observed = observe_started(
            spec,
            started.allocation,
            self._state,
            target.worker.writer,
            self._evidence,
            control,
        )
        try:
            if observed.controller != started.controller:
                raise OwnershipConflict(
                    "Independent controller observation differs from handoff"
                )
            self._scope(spec, op, control)
        except BaseException as error:
            setattr(error, "generator_step_evidence_ref", observed.evidence)
            raise
        if self._pin is None:
            try:
                self._pin = pin_user_tree(observed.controller.target.worker, control)
            except BaseException as error:
                retain_step_failure(
                    self._evidence, self._state, "started", [], [], error
                )
                raise
        self._observations.append(observed.evidence)
        self._started = observed

    def _verify_closed(
        self,
        spec: GeneratorResourceSpec,
        cleanup: GeneratorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> GeneratorStepClosed | None:
        self._scope(spec, op, control, cleanup=True)
        cleanup = GeneratorStepCleanup.model_validate(cleanup)
        if not self._authorized or self._started is None or self._state.target is None:
            raise OwnershipConflict(
                "No independently observed original target; retain quarantine"
            )
        if (
            not cleanup.start_attempted
            or cleanup.target != self._state.target
            or cleanup.launcher != self._state.launcher
        ):
            raise OwnershipConflict("Cleanup differs from original authority handle")
        if cleanup.started is not None:
            same_allocation(spec.slurm.allocation, cleanup.started.allocation)
            if cleanup.started.controller != self._started.controller:
                raise OwnershipConflict("Closure differs from acquisition target")
        # Single owner of the live closure observation: do not spend another
        # shared-filesystem read before capturing the disappearing original tree.
        observed = observe_closed(
            spec, self._state, termination, self._evidence, control, self._pin
        )
        if observed is None:
            raise OwnershipConflict("Independent closure has no original target")
        try:
            if (
                observed.target != self._state.target
                or observed.quiescence.observer != spec.slurm.allocation.facts.writer
            ):
                raise OwnershipConflict("Closure differs from original owner/target")
            self._scope(spec, op, control, cleanup=True)
        except BaseException as error:
            setattr(error, "generator_step_evidence_ref", observed.evidence)
            raise
        self._observations.append(observed.evidence)
        self._closed = observed
        return observed

    def verify_closed(
        self,
        spec: GeneratorResourceSpec,
        cleanup: GeneratorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> GeneratorStepClosed | None:
        self._owned_scope(spec, op, cleanup=True)
        cleanup = GeneratorStepCleanup.model_validate(cleanup)
        if (
            cleanup.target != self._state.target
            or cleanup.launcher != self._state.launcher
        ):
            raise OwnershipConflict("Cleanup differs from original authority handle")
        primary: BaseException | None = None
        try:
            return self._verify_closed(spec, cleanup, termination, op, control)
        except BaseException as error:
            primary = error
            raise
        finally:
            pinned, self._pin = self._pin, None
            if pinned is not None:
                try:
                    pinned.close()
                except BaseException as error:
                    combined = BaseExceptionGroup(
                        "Original verification and handle cleanup failed",
                        ([primary] if primary is not None else []) + [error],
                    )
                    reference = getattr(primary, "generator_step_evidence_ref", None)
                    if reference is None and self._closed is not None:
                        reference = self._closed.evidence
                    if reference is not None:
                        setattr(combined, "generator_step_evidence_ref", reference)
                    raise combined from None
