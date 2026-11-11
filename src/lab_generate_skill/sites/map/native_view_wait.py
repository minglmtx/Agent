"""Wait once for the original selected native view; no navigation or public readout."""

from typing import Any
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.task import PublicTask
from .native_view_scripts import READ, READINESS
from .native_view_rules import readiness_arguments, ready_signal, native_zoom
from .navigation_initial_rules import navigation_readiness_arguments


class NativeViewWait:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.attempted = False
        self.last_signal: dict[str, Any] | None = None
        self.last_signal_raw: object = None
        self.last_view: object = None
        self.settled_seconds = 0.0

    def wait(self, page: Any, control: OperationControl) -> None:
        self._wait(page, control, readiness_arguments())

    def wait_navigation(
        self, page: Any, task: PublicTask, control: OperationControl
    ) -> None:
        self._wait(page, control, navigation_readiness_arguments(task))

    def _wait(self, page: Any, control: OperationControl, args: dict[str, Any]) -> None:
        if self.attempted:
            raise InvalidTransition("Original native view wait already attempted")
        self.attempted = True
        expires = self.clock.monotonic() + 45.0

        def remaining() -> float:
            left = min(control.checkpoint(), expires - self.clock.monotonic())
            if left <= 0:
                raise TimeoutError(
                    "Native map did not settle within its original readiness budget"
                )
            return left

        page.wait_for_function(
            "args => (" + READINESS + ")(args).ready",
            arg=args,
            timeout=remaining() * 1000,
        )
        previous = None
        stable_since = None
        while True:
            remaining()
            self.last_signal_raw = page.evaluate(READINESS, args)
            signal = ready_signal(self.last_signal_raw, directions=args["directions"])
            self.last_signal = signal
            now = self.clock.monotonic()
            remaining()
            if signal != previous or signal["ready"] is not True:
                previous, stable_since = signal, now
            elif stable_since is not None and now - stable_since >= 0.75:
                self.last_view = page.evaluate(READ)
                native_zoom(self.last_view)
                remaining()
                self.settled_seconds = now - stable_since
                return
            page.wait_for_timeout(min(100, remaining() * 1000))
