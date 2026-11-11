"""Compose native transport and full page facts at the existing process port."""

from typing import Any
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_route_collector import MapNativeRequestCollector
from .native_surface_capture import NativeSurfaceCapture
from .native_served_capture import NativeServedCapture
from .native_notes_capture import NativeNotesCapture


class MapNativeProcessCollector:
    def __init__(
        self,
        requests: MapNativeRequestCollector,
        *,
        served: NativeServedCapture | None = None,
        notes: NativeNotesCapture | None = None,
    ) -> None:
        self.requests = requests
        self.surface = NativeSurfaceCapture(
            requests.plan,
            requests.relay.sink,
            requests.relay.evidence_control,
        )
        self.closed = False
        self.final_captured = False
        if served is not None and (
            served.plan != requests.plan
            or served.sink is not requests.relay.sink
            or served.origin != requests.relay.origin
        ):
            raise OwnershipConflict(
                "Served proof must use the original collector plan, sink and origin"
            )
        self.served = served
        if notes is not None and (
            notes.plan != requests.plan
            or notes.sink is not requests.relay.sink
            or notes.origin != requests.relay.origin
        ):
            raise OwnershipConflict(
                "Notes capture must use original plan, sink and origin"
            )
        self.notes = notes

    def _open(self) -> None:
        if self.closed:
            raise InvalidTransition("Original Map process collector is closed")
        self.surface.healthy()
        if self.served is not None:
            self.served.healthy()

    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None:
        self._open()
        self.requests.attach(page, spec, control)
        self.surface.bind(page)
        if self.served is not None:
            self.served.attach(page, control)
        if self.notes is not None:
            self.notes.attach(page, control)

    def before_action(self, control: OperationControl) -> None:
        self._open()
        if self.notes is not None:
            self.notes.healthy()
        self.requests.before_action(control)

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        self._open()
        self.requests.observe(page, readout, control)
        self.surface.capture(page, readout, control, phase="unique_return")
        if self.notes is not None:
            self.notes.observe(page, readout, control)
        self._verify_served(page, readout, control)

    def finish(self, control: OperationControl) -> None:
        """Settle only existing work, then capture limits against the last return."""
        self._open()
        if self.notes is not None:
            self.notes.healthy()
        if self.final_captured:
            return
        readout = self.requests.last_readout
        if readout is None:
            raise InvalidTransition("A real original return is required before finish")
        self.requests.finish(control)
        self.surface.capture(self.requests.page, readout, control, phase="terminal")
        if self.notes is not None:
            self.notes.observe(self.requests.page, readout, control)
        self._verify_served(self.requests.page, readout, control)
        self.final_captured = True

    def _verify_served(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        if (
            self.served is not None
            and self.served.state != "verified"
            and self.surface.last_map_visible
        ):
            self.served.verify(page, readout, control)

    def close(self, control: OperationControl) -> None:
        # A failed surface read must never prevent original transport shutdown.
        self.surface.require_owner()
        self.closed = True
        errors: list[BaseException] = []
        closures = [self.requests.close, self.surface.close]
        if self.served is not None:
            closures.append(self.served.close)
        if self.notes is not None:
            closures.append(self.notes.close)
        for close in closures:
            try:
                close(control)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise BaseExceptionGroup("Original Map process close errors", errors)
