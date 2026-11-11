"""One durable consumed-call marker. It never permits replay or re-creation."""

from pathlib import Path
from lab_generate_skill.domain.local_actor import LocalActorCall
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.processes.wire_json import json_object


def consume_call(root: Path, call: LocalActorCall, control: OperationControl) -> None:
    call = LocalActorCall.model_validate(call)
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise EvidenceIntegrityError("Actor call root must be trusted and canonical")
    raw = call.model_dump_json().encode()
    state = AtomicSnapshotFile(
        root, call.key + ".local-actor-call.json", max_bytes=65536
    )
    with state.locked(control) as transaction:
        prior = transaction.read()
        birth = transaction.pending("0" * 64)
        if prior is not None:
            json_object(prior)
            value = LocalActorCall.model_validate_json(prior)
            if value.model_dump_json().encode() != prior or birth != prior:
                raise EvidenceIntegrityError(
                    "Actor call marker or original birth changed"
                )
            if value != call:
                raise OwnershipConflict(
                    "Original Actor request cannot change its binding"
                )
            raise DispatchAlreadyCommitted(
                "Original Actor call is consumed; inspect retained facts without resending"
            )
        if birth is not None:
            raise EvidenceIntegrityError("Used Actor call cannot be recreated")
        transaction.retain_pending("0" * 64, raw)
        transaction.write(raw)
        transaction.checkpoint()
    # Only the original caller reaching this return may send once. Unknown
    # transaction release/acknowledgement also leaves the marker consumed.
