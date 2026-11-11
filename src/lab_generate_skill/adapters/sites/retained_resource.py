"""Late, once-only ownership of the existing registered site and journal.

The pure outer scope starts nothing. TaskPreparation opens the original manager
after the canonical task once/acquiring gate; outer exit follows task recovery.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    ResourceJournal,
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.site_resources import SiteResourceAuthority
from lab_generate_skill.ports.site_tasks import SiteTasks
from lab_generate_skill.ports.site_capture import ParentSiteCapture
from lab_generate_skill.ports.site_resume import ParentSiteResume
from .resource import registered_site, RegisteredSite
from .resource_records import phase
from .retained_closure import original_closed_site


class RetainedSiteResource:
    def __init__(
        self,
        spec: SiteResourceSpec,
        operation: OperationContext,
        *,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        authority: SiteResourceAuthority,
        cleanup_seconds: int = 30,
    ) -> None:
        if type(cleanup_seconds) is not int or not 1 <= cleanup_seconds <= 3600:
            raise ValueError("Explicit bounded site metadata cleanup duration required")
        self.cleanup_seconds = cleanup_seconds
        self.spec = SiteResourceSpec.model_validate(spec)
        self.operation = OperationContext.model_validate(operation)
        self.spec.check_operation(self.operation, "execute")
        if any(x is None for x in (journal, evidence, controls, clock, authority)):
            raise ValueError("All original site ownership dependencies are mandatory")
        self.journal, self.evidence, self.controls, self.clock, self.authority = (
            journal,
            evidence,
            controls,
            clock,
            authority,
        )
        self.owner = os.getpid(), threading.get_ident()
        self.phase = "new"
        self.manager: AbstractContextManager[RegisteredSite] | None = None
        self._registered: RegisteredSite | None = None
        self.open_error: BaseException | None = None
        self.close_error: BaseException | None = None
        self.closed: ResourceRecord | None = None
        self._registration_entered = False

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Site handle changed original process/thread")

    @property
    def site(self) -> SiteResourceStarted:
        self._owner()
        if self._registered is None:
            raise OwnershipConflict("Original site startup has not returned")
        return self._registered.site

    def _open(self) -> RegisteredSite:
        self._owner()
        if self.phase != "open" or self._registered is None:
            raise OwnershipConflict("Original registered site is not open")
        return self._registered

    @property
    def tasks(self) -> SiteTasks:
        return self._open().tasks

    @property
    def capture(self) -> ParentSiteCapture:
        return self._open().capture

    @property
    def resume(self) -> ParentSiteResume:
        return self._open().resume

    def _enter_registration(self) -> None:
        self._owner()
        if self.phase != "opening" or self._registration_entered:
            raise OwnershipConflict("Site registration changed its original opening")
        self._registration_entered = True

    def open(self, control: OperationControl) -> RegisteredSite:
        self._owner()
        if self.phase != "new":
            raise DispatchAlreadyCommitted(
                "Original site acquisition attempted; never reacquire"
            )
        self.phase = "opening"
        try:
            control.checkpoint()
            self.manager = registered_site(
                self.spec,
                self.operation,
                journal=self.journal,
                evidence=self.evidence,
                controls=self.controls,
                clock=self.clock,
                authority=self.authority,
                cleanup_seconds=self.cleanup_seconds,
                registration_boundary=self._enter_registration,
            )
            self._registered = self.manager.__enter__()
            self.phase = "open"
            control.checkpoint()
            return self._registered
        except BaseException as error:
            self.open_error = error
            if self._registered is None:
                self.phase = (
                    "start-unconfirmed"
                    if self._registration_entered
                    else "registration-not-entered"
                )
            raise

    def _finish(self, primary: BaseException | None) -> None:
        self._owner()
        if self.phase == "open":
            assert self.manager is not None
            self.phase = "closing"
            try:
                self.manager.__exit__(
                    type(primary) if primary is not None else None,
                    primary,
                    primary.__traceback__ if primary is not None else None,
                )
            finally:
                self.phase = "ended"

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
            raise OwnershipConflict("Site cleanup changed original acquisition parent")
        if primary is not None and not isinstance(primary, BaseException):
            raise TypeError("Original site failure must be an exception or None")
        if self.phase in ("new", "opening", "closing", "registration-not-entered"):
            raise DispatchAlreadyCommitted("No confirmed owned site to finalize")
        try:
            self._finish(primary)
            self.closed = original_closed_site(
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
            self.phase = "close-unconfirmed"
            raise

    def _exit(self, primary: BaseException | None) -> None:
        if self.phase in ("new", "closed", "registration-not-entered"):
            return
        try:
            operation = self.operation.cleanup(
                phase(self.operation, "retained-close-read").operation_id,
                now=self.clock.utcnow(),
                seconds=self.cleanup_seconds,
            )
            control = self.controls.bind(operation)
        except BaseException as prelude:
            errors = ([primary] if primary is not None else []) + [prelude]
            try:
                self._finish(primary)
            except BaseException as physical:
                errors.append(physical)
            self.phase = "close-unconfirmed"
            self.close_error = (
                errors[0]
                if len(errors) == 1
                else BaseExceptionGroup(
                    "Site close prelude and original physical cleanup", errors
                )
            )
            raise self.close_error
        self.close(operation, control, primary=primary)

    @contextmanager
    def scope(self) -> Iterator[object]:
        self._owner()
        try:
            yield self
        except BaseException as primary:
            try:
                self._exit(primary)
            except BaseException as cleanup:
                raise BaseExceptionGroup(
                    "Original task and site closure", [primary, cleanup]
                ) from None
            raise
        else:
            self._exit(None)
