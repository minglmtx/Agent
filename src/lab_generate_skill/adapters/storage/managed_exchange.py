"""Execute once, then attempt independent bounded resolution even after a stop.

Transport errors before its launch boundary have no effects. After launch,
only a confirmed independent absence proof can release the store for different
cleanup I/O; the failed original operation is never retried. This composition
does not delete temporaries or recover a dead controller.
"""

from uuid import uuid4
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)
from lab_generate_skill.adapters.processes.exception_facts import exception_chain
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from .registered_protocol import RegisteredStorageCommand
from .registered_transport import (
    RegisteredStorageExecution,
    RegisteredStorageFailure,
    RegisteredStorageTransport,
)
from .resolver_protocol import StorageResolutionCommand
from .resolver_transport import StorageResolutionExecution, StorageResolverTransport
from .managed_result import ManagedEvidenceResult


def execute_managed_exchange(
    command: RegisteredStorageCommand,
    payload: bytes,
    control: OperationControl,
    transport: RegisteredStorageTransport,
    resolver: StorageResolverTransport,
    clock: Clock,
    cleanup_controls: OperationControls,
    cleanup_seconds: float,
    expected_snapshot: EvidenceSessionSnapshot | None = None,
) -> ManagedEvidenceResult:
    execution: RegisteredStorageExecution | None = None
    failed: RegisteredStorageFailure | None = None
    resolution: StorageResolutionExecution | None = None
    primary: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        execution = transport.execute(command, payload, control)
    except BaseException as error:
        primary = error
        for item in exception_chain(error):
            candidate = getattr(item, "registered_storage", item)
            if isinstance(candidate, RegisteredStorageFailure):
                failed = candidate
                break
    attempted = execution is not None or failed is not None
    if attempted:
        try:
            ending = (
                execution.ending
                if execution is not None
                else (failed.ending if failed is not None else None)
            )
            cleanup = command.operation.cleanup(
                "evidence-resolve-" + uuid4().hex,
                now=clock.utcnow(),
                seconds=cleanup_seconds,
            )
            resolution = resolver.execute(
                StorageResolutionCommand(
                    original=command, cleanup=cleanup, ending=ending
                ),
                payload,
                cleanup_controls.bind(cleanup),
            )
            if resolution.result.reply.not_registered is not None and (
                expected_snapshot is None
                or resolution.result.snapshot != expected_snapshot
            ):
                raise OwnershipConflict(
                    "Unregistered exchange history differs from original acknowledged snapshot"
                )
        except BaseException as error:
            cleanup_error = error
    return ManagedEvidenceResult(
        command,
        execution,
        failed,
        resolution,
        primary,
        cleanup_error,
        attempted,
        (
            expected_snapshot
            if resolution is not None
            and resolution.result.reply.not_registered is not None
            else None
        ),
    )
