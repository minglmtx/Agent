"""Retained real bytes, explicit synthetic live-store edge; no historical grant."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.plans.closed_actor_inputs import (
    SupervisedActorAcquisitionReads,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    ClosedSourceReadReply,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionBodies
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from test_closed_actor_acquisition import retained
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "reference",
        "storage",
        "cancel",
        "partial",
        "thread",
        "attempt",
        "reader",
    ],
)
def test_original_actor_bodies_pass_with_fresh_current_gate(fault: str) -> None:
    material, root, selection = retained()
    store = ReadOnlyEvidence(root, max_object_bytes=64 * 1024**2)
    bounded = guard(60)
    bodies = ActorAcquisitionBodies(
        selection=selection,
        intent_json=store.read(selection.intent_ref, bounded).decode(),
        spec_json=store.read(selection.binding.spec_ref, bounded).decode(),
        acquired_json=store.read(selection.binding.acquired_ref, bounded).decode(),
    )
    owner = material.site.token.owner
    op = OperationContext(
        operation_id="unit-task-acquisition-inputs",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        attempt_id="unit-task",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )

    class Transport(ClosedSourceReadTransport):
        def __init__(self) -> None:
            self.loads = self.current = self.owners = 0
            self.last_reply = None

        def require_current(self, *args: Any, **kwargs: Any) -> None:
            self.owners += 1  # Deliberate unit current-owner premise, never a grant.

        def read(self, *args: Any, **kwargs: Any) -> Any:
            self.loads += 1
            if fault == "partial":
                raise OSError("Original acquired-body proof unconfirmed")
            self.last_reply = cast(
                ClosedSourceReadReply, SimpleNamespace(actor_bodies=bodies)
            )

        def check_current(self, control: OperationControl) -> None:
            control.checkpoint()
            self.current += 1
            if fault == "storage":
                raise PermissionError("Original storage revoked")
            if fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)

    transport = Transport()
    reader = SupervisedActorAcquisitionReads(material, transport)

    def consume() -> None:
        with reader.task_scope(op):
            assert reader.read_original(selection, op, bounded) == bodies
            current = selection
            next_op = op
            if fault == "reference":
                current = selection.model_copy(
                    update={
                        "intent_ref": selection.intent_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
            elif fault == "attempt":
                next_op = op.model_copy(update={"attempt_id": "other"})
            elif fault == "reader":
                reader.transport = Transport()
            elif fault == "thread":
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(reader.read_original, selection, op, bounded).result()
            assert reader.read_original(current, next_op, bounded) == bodies
            assert reader.read_original(current, next_op, bounded) == bodies

    if fault == "none":
        consume()
        assert (transport.loads, transport.current, transport.owners) == (1, 2, 3)
        assert reader.read_original(selection, op, bounded) == bodies
        assert transport.loads == 2  # Independent reads obtain their own proof.
    else:
        with pytest.raises(
            (OwnershipConflict, PermissionError, OperationStopped, OSError)
        ):
            consume()
        assert transport.loads == 1
    assert reader._bodies is None and reader._task is None
    with pytest.raises(OwnershipConflict):
        with reader.task_scope(op):
            pass
