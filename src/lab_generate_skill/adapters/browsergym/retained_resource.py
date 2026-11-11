"""Retain the existing registered browser between initialization and finalization.

This is an owner-local handle over the original ResourceJournal/context manager,
not another launcher or ledger. Opening does not admit an Actor. The original
authority still proves physical closure; this handle only reads its ending.
"""

from contextlib import AbstractContextManager
import os
import threading
from types import TracebackType
from typing import Literal
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.ports.browser_resources import BrowserResourceAuthority
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
    ResourceJournal,
)
from .evidence_session import EvidenceBrowserSession
from .resource import registered_browser
from .retained_closure import original_closed_browser
from .resource_records import phase
from .return_publication import BrowserReturnPublication


class RetainedBrowserResource:
    def __init__(
        self,
        spec: BrowserResourceSpec,
        operation: OperationContext,
        *,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        authority: BrowserResourceAuthority,
        cleanup_seconds: int = 30,
        return_publication: BrowserReturnPublication | None = None,
    ) -> None:
        if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
            raise ValueError(
                "Explicit bounded browser metadata cleanup duration required"
            )
        self.cleanup_seconds = cleanup_seconds
        self.spec = BrowserResourceSpec.model_validate(spec)
        self.operation = OperationContext.model_validate(operation)
        self.spec.check_operation(self.operation, "execute")
        if (
            return_publication is not None
            and return_publication.token != self.spec.token
        ):
            raise OwnershipConflict("Return publication changed browser allocation")
        self.return_publication = return_publication
        if any(x is None for x in (journal, evidence, controls, clock, authority)):
            raise ValueError(
                "Original browser journal, IO, controls, clock and authority are mandatory"
            )
        self.journal, self.evidence, self.controls, self.clock = (
            journal,
            evidence,
            controls,
            clock,
        )
        self.authority = authority
        self.owner = os.getpid(), threading.get_ident()
        self.phase = "new"
        self.manager: AbstractContextManager[EvidenceBrowserSession] | None = None
        self._session: EvidenceBrowserSession | None = None
        self.open_error: BaseException | None = None
        self.close_error: BaseException | None = None
        self.closed: ResourceRecord | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Browser handle changed original process/thread")

    @property
    def session(self) -> EvidenceBrowserSession:
        self._owner()
        if self.phase != "open" or self._session is None:
            raise OwnershipConflict("Original acquired browser is not open")
        return self._session

    def open(self, control: OperationControl) -> EvidenceBrowserSession:
        self._owner()
        if self.phase != "new":
            raise DispatchAlreadyCommitted(
                "Browser acquisition was already attempted; never reacquire"
            )
        self.phase = "opening"
        try:
            control.checkpoint()
            self.manager = registered_browser(
                self.spec,
                self.operation,
                journal=self.journal,
                evidence=self.evidence,
                controls=self.controls,
                clock=self.clock,
                authority=self.authority,
                cleanup_seconds=self.cleanup_seconds,
                return_publication=self.return_publication,
            )
            self._session = self.manager.__enter__()
            self.phase = "open"
            control.checkpoint()
            return self._session
        except BaseException as error:
            self.open_error = error
            # A returned session remains owned even if caller cancellation is
            # noticed after acquisition. Finalization must still close it.
            if self._session is None:
                self.phase = "start-unconfirmed"
            raise

    def close(
        self,
        operation: OperationContext,
        control: OperationControl,
        *,
        primary: BaseException | None = None,
    ) -> ResourceRecord:
        self._owner()
        operation = OperationContext.model_validate(operation)
        self.spec.check_operation(operation, "cleanup")
        if operation.parent_operation_id != self.operation.operation_id:
            raise OwnershipConflict(
                "Browser cleanup must retain original acquisition parent"
            )
        if primary is not None and not isinstance(primary, BaseException):
            raise TypeError("Original browser failure must be an exception or None")
        if self.phase in ("new", "opening", "closing"):
            raise DispatchAlreadyCommitted("No confirmed owned browser to finalize")
        try:
            self._finish(primary)
            self.closed = original_closed_browser(
                self.spec,
                self.operation,
                operation,
                self.journal,
                self.evidence,
                control,
            )
            self.phase = "closed"
            return self.closed
        except BaseException as error:
            self.close_error = error
            # The manager has already terminated (or its enter failed). Future
            # close can only inspect the original record, never exit it again.
            self.phase = "close-unconfirmed"
            raise

    def _finish(self, primary: BaseException | None) -> None:
        self._owner()
        if self.phase == "open":
            assert self.manager is not None
            self.phase = "closing"
            try:
                # Physical cleanup is attempted before caller checkpoint;
                # its original bounded cleanup controls remain independent.
                self.manager.__exit__(
                    type(primary) if primary is not None else None,
                    primary,
                    primary.__traceback__ if primary is not None else None,
                )
            finally:
                self.phase = "ended"

    def __enter__(self) -> EvidenceBrowserSession:
        return self.open(self.controls.bind(self.operation))

    def __exit__(
        self,
        kind: type[BaseException] | None,
        primary: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self._owner()
        try:
            operation = self.operation.cleanup(
                phase(self.operation, "retained-close-read").operation_id,
                now=self.clock.utcnow(),
                seconds=self.cleanup_seconds,
            )
            control = self.controls.bind(operation)
        except BaseException as prelude_error:
            errors = ([primary] if primary is not None else []) + [prelude_error]
            try:
                self._finish(primary)
            except BaseException as physical_error:
                errors.append(physical_error)
            self.phase = "close-unconfirmed"
            self.close_error = (
                errors[0]
                if len(errors) == 1
                else BaseExceptionGroup(
                    "Browser finalization prelude and original physical cleanup", errors
                )
            )
            raise self.close_error
        self.close(operation, control, primary=primary)
        return False
