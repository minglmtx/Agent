"""One original per-task browser handle, retained before any acquisition.

This is owner-local composition state, not a launcher or persistent ledger.
An interrupted factory is deliberately not evidence of physical non-start.
"""

import os
import threading
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.ports.lifecycle import ResourceJournal
from .retained_resource import RetainedBrowserResource


class OriginalTaskBrowserOwner:
    def __init__(self, token: AllocationToken, journal: ResourceJournal) -> None:
        self.token = AllocationToken.model_validate(token)
        if (
            self.token.resource_kind != "browser"
            or self.token.scope != "attempt"
            or journal is None
        ):
            raise ValueError("Original attempt browser token/journal required")
        self.journal = journal
        self.owner = os.getpid(), threading.get_ident()
        self.constructing = self.sealed = False
        self._browser: RetainedBrowserResource | None = None

    def _caller(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Task browser holder changed original controller")

    def begin(self) -> None:
        self._caller()
        if self.constructing or self._browser is not None or self.sealed:
            raise OwnershipConflict("Original browser factory is one-shot")
        self.constructing = True

    def retain(self, browser: RetainedBrowserResource) -> None:
        self._caller()
        if not isinstance(browser, RetainedBrowserResource):
            raise TypeError("Original retained browser required")
        if (
            not self.constructing
            or self._browser is not None
            or self.sealed
            or browser.owner != self.owner
            or browser.phase != "new"
            or browser.manager is not None
            or browser.spec.token != self.token
            or browser.journal is not self.journal
        ):
            raise OwnershipConflict(
                "Retain original unstarted browser before any acquisition"
            )
        self._browser, self.constructing = browser, False

    def original(self) -> RetainedBrowserResource | None:
        self._caller()
        return self._browser

    def seal_unstarted(self) -> RetainedBrowserResource | None:
        self._caller()
        b = self._browser
        if (
            self.sealed
            or self.constructing
            or (
                b is not None
                and (
                    b.phase != "new"
                    or b.manager is not None
                    or b.open_error is not None
                )
            )
        ):
            raise OwnershipConflict(
                "Interrupted or started browser cannot prove non-start"
            )
        self.sealed = True
        # RetainedBrowserResource.open refuses this terminal owner phase. No
        # registered resource or fabricated acquisition/closing event is added.
        if b is not None:
            b.phase = "unstarted-sealed"
        return b
