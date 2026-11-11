"""Public-store invocation evidence, including uncertain effects and both errors.

No payload or credentials are included. Original transport captures may contain
private evidence and must stay in the trusted diagnostic path.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.errors import EvidenceError
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from .registered_protocol import RegisteredStorageCommand
from .registered_transport import RegisteredStorageExecution, RegisteredStorageFailure
from .resolver_transport import StorageResolutionExecution


@dataclass(frozen=True)
class ManagedEvidenceResult:
    command: RegisteredStorageCommand
    execution: RegisteredStorageExecution | None
    failed_execution: RegisteredStorageFailure | None
    resolution: StorageResolutionExecution | None
    primary: BaseException | None
    cleanup_error: BaseException | None
    attempted: bool
    expected_snapshot: EvidenceSessionSnapshot | None = None

    @property
    def snapshot(self) -> EvidenceSessionSnapshot | None:
        return None if self.resolution is None else self.resolution.result.snapshot

    @property
    def reusable(self) -> bool:
        snapshot = self.snapshot
        absent = (
            None
            if self.resolution is None
            else self.resolution.result.reply.not_registered
        )
        if absent is not None:
            failed = self.failed_execution
            return (
                self.execution is None
                and self.primary is not None
                and self.cleanup_error is None
                and failed is not None
                and failed.ending == absent.ending
                and (
                    failed.result is None
                    or (
                        failed.result.reply.intent is None
                        and failed.result.reply.outcome is None
                        and failed.result.snapshot is None
                    )
                )
                and snapshot is not None
                and self.expected_snapshot is not None
                and snapshot == self.expected_snapshot
                and snapshot.binding == self.command.binding
                and snapshot.revision == self.command.expected_revision
                and self.command.io is not None
                and absent.exchange_id == self.command.io.exchange_id
                and not any(
                    e.intent.exchange_id == absent.exchange_id for e in snapshot.entries
                )
                and (not snapshot.entries or snapshot.entries[-1].reusable)
            )
        return (
            snapshot is not None
            and bool(snapshot.entries)
            and self.command.io is not None
            and snapshot.entries[-1].intent.exchange_id == self.command.io.exchange_id
            and snapshot.entries[-1].reusable
        )

    def raise_errors(self) -> None:
        errors = [e for e in (self.primary, self.cleanup_error) if e is not None]
        if not errors and not self.reusable:
            errors.append(EvidenceError("Storage remains isolated after resolution"))
        if errors:
            error = (
                errors[0]
                if len(errors) == 1
                else BaseExceptionGroup(
                    "Evidence operation and independent cleanup failed", errors
                )
            )
            setattr(error, "managed_evidence", self)
            raise error
