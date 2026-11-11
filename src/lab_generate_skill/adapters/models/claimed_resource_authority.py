"""Original claimed Actor allocation and one owned GPU-domain closure observation.

Uses the existing provider/step/held-cgroup algorithms. Its enclosing scope
releases observation handles even when unconfirmed termination or bookkeeping
failure skips verify_closed. Releasing a handle grants no closure receipt.
"""

import os
import threading
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree, pin_user_tree
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import (
    ActorStepStarted,
    ActorStepCleanup,
    ActorStepClosed,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from .actor_resource_records import check_operation
from .actor_step import ActorStepState, observe_closed, same_allocation


class ClaimedActorResourceAuthority:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        spec: ActorResourceSpec,
        acquisition: OperationContext,
    ) -> None:
        if not isinstance(owner, ClaimedRunResourceOwner):
            raise TypeError("Original claimed execution owner required")
        self.owner, self.spec, self.acquisition = (
            owner,
            ActorResourceSpec.model_validate(spec),
            OperationContext.model_validate(acquisition),
        )
        check_operation(self.spec, self.acquisition, "execute")
        self._pin: PinnedUserTree | None = None
        self.started: ActorStepStarted | None = None
        self.start_attempted = self.close_attempted = False
        self._context = (os.getpid(), threading.get_ident())
        self._active = self._scope_used = False

    def __enter__(self) -> "ClaimedActorResourceAuthority":
        if self._context != (os.getpid(), threading.get_ident()) or self._scope_used:
            raise OwnershipConflict("Original Actor authority scope cannot be replayed")
        self.owner.authority.require_caller(self.acquisition)
        self._active = self._scope_used = True
        return self

    def __exit__(
        self, error_type: object, primary: BaseException | None, traceback: object
    ) -> None:
        if self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Foreign caller cannot release Actor observations")
        self._active = False
        self._release_pin(primary)

    def _scope(self) -> None:
        if not self._active or self._context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Original Actor authority scope is inactive or foreign"
            )

    def _release_pin(self, primary: BaseException | None) -> None:
        held, self._pin = self._pin, None
        if held is not None:
            try:
                held.close()
            except BaseException as error:
                raise BaseExceptionGroup(
                    "Original Actor verification and pin cleanup failed",
                    ([primary] if primary else []) + [error],
                ) from None

    def authorize_start(
        self, spec: ActorResourceSpec, op: OperationContext, control: OperationControl
    ) -> None:
        self._scope()
        if spec != self.spec or op != self.acquisition or self.start_attempted:
            raise OwnershipConflict("Original Actor acquisition permission is one-shot")
        check_operation(spec, op, "execute")
        self.owner.caller(op, control)
        self.start_attempted = True
        self.owner.model(spec, op, control, new_work=True)

    def verify_started(
        self,
        spec: ActorResourceSpec,
        started: ActorStepStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self._scope()
        if (
            spec != self.spec
            or op != self.acquisition
            or not self.start_attempted
            or self.started is not None
            or self.close_attempted
        ):
            raise OwnershipConflict("Original Actor worker cannot be rebound")
        self.owner.model(spec, op, control, new_work=True)
        same_allocation(spec.slurm.allocation, started.allocation)
        target = started.controller.target
        if (
            observe_process_cgroup(
                self.owner.authority.execution, target.worker.writer, control
            ).membership
            != target.worker
        ):
            raise OwnershipConflict(
                "Actor worker changed its original physical allocation"
            )
        self._pin = pin_user_tree(target.worker, control)
        self.started = ActorStepStarted.model_validate(started)

    def verify_closed(
        self,
        spec: ActorResourceSpec,
        cleanup: ActorStepCleanup,
        termination: ProcessTermination,
        op: OperationContext,
        control: OperationControl,
    ) -> ActorStepClosed | None:
        self._scope()
        if spec != self.spec or self.close_attempted:
            raise OwnershipConflict("Original Actor closure permission is one-shot")
        check_operation(spec, op, "cleanup")
        if op.parent_operation_id != self.acquisition.operation_id:
            raise OwnershipConflict("Actor cleanup changed original acquisition parent")
        if self.started is not None and cleanup.started != self.started:
            raise OwnershipConflict("Actor cleanup replaced original acquired worker")
        self.owner.caller(op, control)
        self.close_attempted = True
        primary: BaseException | None = None
        try:
            check_operation(spec, op, "cleanup")
            if op.parent_operation_id != self.acquisition.operation_id:
                raise OwnershipConflict(
                    "Actor cleanup changed original acquisition parent"
                )
            permission_error: BaseException | None = None
            try:
                self.owner.model(spec, op, control, new_work=False)
            except BaseException as error:
                permission_error = error
            try:
                closed = observe_closed(
                    spec,
                    ActorStepState(
                        start_attempted=cleanup.start_attempted,
                        launcher=cleanup.launcher,
                        target=cleanup.target,
                        started=cleanup.started,
                    ),
                    termination,
                    self.owner.evidence,
                    control,
                    self._pin,
                )
            except BaseException as error:
                if permission_error is not None:
                    raise BaseExceptionGroup(
                        "Original Actor permission and physical closure failed",
                        [permission_error, error],
                    ) from None
                raise
            if permission_error is not None:
                if closed is not None:
                    setattr(
                        permission_error, "actor_step_evidence_ref", closed.evidence
                    )
                raise permission_error
            if closed is None and (
                termination.state != "not_started" or cleanup.start_attempted
            ):
                raise OwnershipConflict(
                    "Unknown Actor start cannot be declared unstarted"
                )
            return closed
        except BaseException as error:
            primary = error
            raise
        finally:
            self._release_pin(primary)
