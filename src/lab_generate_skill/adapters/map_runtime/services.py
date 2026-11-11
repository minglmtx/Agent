"""Retain original per-service groups; only Rails may acquire a replacement.

Each generation delegates native spawn, pin, quiescence and close to the common
owned process adapter. No numeric PID signals, replacement of unknown handles,
root deletion or port release. Registered worker authority remains outside.
"""

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import re
import threading
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from lab_generate_skill.domain.map_frontend_lifecycle import MapFrontendStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_quiescence import QuiescentNativeServices
from lab_generate_skill.ports.map_services import MapStartupControls
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.adapters.map_artifacts.files import private_directory
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory


@dataclass
class ServiceGeneration:
    name: str
    number: int
    argv: tuple[str, ...]
    group: QuiescentNativeServices | None = None
    pin: NativeNamespaceIdentity | None = None
    retirement: MapFrontendStopped | None = None
    retire_attempted: bool = False
    grace_error: OperationStopped | None = None
    stop_attempted: bool = False
    stop_facts: tuple[NativeServiceExit, ...] | None = None
    stop_error: BaseException | None = None


class OwnedMapServices:
    def __init__(
        self,
        log_root: Path,
        limits: MapStartupControls,
        *,
        factory: Callable[[Path], QuiescentNativeServices] = LocalNativeServices,
    ) -> None:
        private_directory(log_root)
        self.log_root, self.limits, self.factory = log_root, limits, factory
        self.owner = os.getpid(), threading.get_ident()
        self.records: list[ServiceGeneration] = []
        self.active: dict[str, ServiceGeneration] = {}
        self.attempted: set[str] = set()
        self.poisoned = False
        self.stopping = False
        self.stop_facts: tuple[NativeServiceExit, ...] | None = None
        self.stop_error: BaseException | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map service group worker/thread required")

    def _available(self) -> None:
        self._owner()
        if self.stopping or self.poisoned:
            raise InvalidTransition("Original Map service group stopping or uncertain")

    def _launch(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        number = sum(r.name == name for r in self.records) + 1
        record = ServiceGeneration(name, number, argv)
        self.records.append(record)
        self.active[name] = record
        try:
            private_directory(self.log_root)
            directory = self.log_root / f"{name}-{number}"
            directory.mkdir(mode=0o700)
            sync_directory(self.log_root)
            record.group = self.factory(directory)  # construction must not spawn
            record.group.start(name, argv, control)
        except BaseException:
            self.poisoned = True
            raise

    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        self._available()
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
            raise ValueError("Exact bounded original service name required")
        if (
            type(argv) is not tuple
            or not argv
            or any(type(a) is not str or "\0" in a for a in argv)
            or not os.path.isabs(argv[0])
        ):
            raise ValueError("Exact original absolute native service argv required")
        if name in self.attempted:
            raise InvalidTransition("Original service start cannot repeat")
        control.checkpoint()
        self.attempted.add(name)
        self._launch(name, argv, control)

    def require_running(self) -> None:
        self._available()
        if not self.active:
            raise InvalidTransition("No current original native service group")
        for record in self.active.values():
            if record.group is None:
                raise InvalidTransition("Original service construction incomplete")
            record.group.require_running()

    def _current(self, name: str) -> ServiceGeneration:
        self._available()
        if type(name) is not str or name not in self.active:
            raise InvalidTransition("Original current service generation required")
        return self.active[name]

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        record = self._current(name)
        if record.pin is not None or record.group is None:
            raise InvalidTransition("Original service must be live and unpinned")
        try:
            record.pin = record.group.pin_namespace(name, control)
            if record.pin.service != name:
                raise OwnershipConflict("Namespace pin changed original service")
            return record.pin
        except BaseException:
            self.poisoned = True
            raise

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        # NativeServices cleanup capability, not a replacement permission.
        self._owner()
        record = self.active.get(name)
        if (
            self.stopping
            or record is None
            or record.group is None
            or record.pin is None
        ):
            raise InvalidTransition("Original held service namespace required")
        self.poisoned = True
        result = record.group.stop_namespace(name, control)
        if result.original != record.pin:
            raise OwnershipConflict("Stop changed original held namespace")
        return result

    def _close(
        self, record: ServiceGeneration, control: OperationControl
    ) -> tuple[NativeServiceExit, ...]:
        if record.stop_facts is not None:
            return record.stop_facts
        if record.stop_attempted:
            raise InvalidTransition(
                "Uncertain native handle close cannot repeat"
            ) from record.stop_error
        record.stop_attempted = True
        try:
            record.stop_facts = (
                () if record.group is None else record.group.stop(control)
            )
            return record.stop_facts
        except BaseException as error:
            record.stop_error = error
            raise

    def retire_frontend(self, control: OperationControl) -> MapFrontendStopped:
        record = self._current("rails_server")
        if record.retire_attempted or record.pin is None or record.group is None:
            raise InvalidTransition("One original pinned Rails retirement required")
        self.require_running()
        control.checkpoint()
        record.retire_attempted = True
        try:
            forced = False
            try:
                quiet = NativeServiceQuiescence.model_validate(
                    record.group.quiesce(self.limits.bind(control, "frontend_grace"))
                )
                if (
                    len(quiet.namespaces) != 1
                    or quiet.namespaces[0].original != record.pin
                ):
                    raise OwnershipConflict(
                        "Rails quiescence changed original namespace"
                    )
                stopped = quiet.namespaces[0]
            except OperationStopped as error:
                # Only the original local grace timeout allows its bounded force
                # phase. Caller cancellation/deadline or any other fault propagates.
                if (error.reason_code, error.operation_id) != (
                    "DEADLINE_EXCEEDED",
                    "map-frontend_grace",
                ):
                    raise
                record.grace_error = error
                control.checkpoint()
                stopped = record.group.stop_namespace(
                    "rails_server", self.limits.bind(control, "frontend_force")
                )
                forced = True
            if stopped.original != record.pin:
                raise OwnershipConflict("Rails stop changed original held namespace")
            facts = self._close(record, control)
            if len(facts) != 1:
                raise OwnershipConflict("Exactly one original Rails master required")
            result = MapFrontendStopped(
                generation=record.number,
                master=facts[0],
                namespace=stopped,
                forced_namespace=forced,
                grace_timeout_operation_id="map-frontend_grace" if forced else None,
            )
            record.retirement = result
            control.checkpoint()
            del self.active["rails_server"]
            return result
        except BaseException:
            self.poisoned = True
            raise

    def replace_frontend(self, control: OperationControl) -> None:
        self._available()
        previous = next(
            (r for r in reversed(self.records) if r.name == "rails_server"), None
        )
        if (
            "rails_server" in self.active
            or previous is None
            or previous.retirement is None
        ):
            raise InvalidTransition("Confirmed original Rails retirement required")
        control.checkpoint()
        self._launch("rails_server", previous.argv, control)

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self._owner()
        if self.stop_facts is not None:
            return self.stop_facts
        if self.stopping:
            raise InvalidTransition(
                "Unknown original Map group stop cannot repeat"
            ) from self.stop_error
        self.stopping = True
        errors: list[BaseException] = []
        facts: tuple[NativeServiceExit, ...] = ()
        for record in reversed(self.records):
            try:
                facts += self._close(record, control)
            except BaseException as error:
                errors.append(error)
        if errors:
            self.stop_error = BaseExceptionGroup(
                "Original Map generation cleanup incomplete", errors
            )
            raise self.stop_error
        self.stop_facts = facts
        return facts
