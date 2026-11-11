"""Use the existing installed readonly graph worker for three immutable bodies."""

from pydantic import TypeAdapter
from collections.abc import Iterator
from contextlib import contextmanager
import os
import threading
from lab_generate_skill.domain.actor_acquisition_inputs import (
    ActorAcquisitionInputs,
    ActorAcquisitionBodies,
)
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .closed_source_transport import ClosedSourceReadTransport


class SupervisedActorAcquisitionReads:
    def __init__(
        self, material: ClosedSourceMaterial, transport: ClosedSourceReadTransport
    ) -> None:
        if not isinstance(transport, ClosedSourceReadTransport):
            raise TypeError("Original installed source reader required")
        self.material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        self.transport = transport
        self._task: OperationContext | None = None
        self._bodies: ActorAcquisitionBodies | None = None
        self._identity: tuple[int, int] | None = None
        self._material: ClosedSourceMaterial | None = None
        self._transport: ClosedSourceReadTransport | None = None
        self._used = False

    @contextmanager
    def task_scope(self, operation: OperationContext) -> Iterator[None]:
        """One original task's immutable acquisition bodies; live gates stay fresh."""
        operation = OperationContext.model_validate(operation)
        owner = self.material.site.token.owner
        if (
            self._used
            or (operation.run_id, operation.owner_id) != (owner.run_id, owner.owner_id)
            or (
                operation.mode != "execute"
                or operation.attempt_id is None
                or operation.allocation_id is not None
                or operation.recovery_ref is not None
            )
        ):
            raise OwnershipConflict("Actor input scope changed original task/owner")
        self._used = True
        self._task, self._material, self._transport = (
            operation,
            self.material,
            self.transport,
        )
        self._identity = os.getpid(), threading.get_ident()
        try:
            yield
        finally:
            self._task = None
            self._bodies = None
            self._material = None
            self._transport = None
            self._identity = None

    def read_original(
        self,
        selection: ActorAcquisitionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> ActorAcquisitionBodies | None:
        selection = ActorAcquisitionInputs.model_validate(selection)
        operation = OperationContext.model_validate(operation)
        control.checkpoint()
        if self._task is not None and (
            self._identity != (os.getpid(), threading.get_ident())
            or self.material != self._material
            or self.transport is not self._transport
            or (operation.run_id, operation.owner_id)
            != (self._task.run_id, self._task.owner_id)
            or operation.attempt_id not in (None, self._task.attempt_id)
        ):
            raise OwnershipConflict("Actor bodies left original task/reader/thread")
        if not selection.supported():
            return None
        if selection.binding.resource.owner != self.material.site.token.owner or (
            operation.run_id,
            operation.owner_id,
        ) != (
            selection.binding.resource.owner.run_id,
            selection.binding.resource.owner.owner_id,
        ):
            raise OwnershipConflict("Actor body proof changed original owner/operation")
        self.transport.require_current(self.material, operation)
        if self._bodies is not None:
            if self._bodies.selection != selection:
                raise OwnershipConflict("Actor task input changed original acquisition")
            self.transport.check_current(control)
            return self._bodies
        self.transport.read(self.material, control, actor_inputs=selection)
        reply = self.transport.last_reply
        if (
            reply is None
            or reply.actor_bodies is None
            or reply.actor_bodies.selection != selection
        ):
            raise OwnershipConflict(
                "Original Actor acquisition body proof missing or changed"
            )
        control.checkpoint()
        if self._task is not None:
            self._bodies = reply.actor_bodies
        return reply.actor_bodies
