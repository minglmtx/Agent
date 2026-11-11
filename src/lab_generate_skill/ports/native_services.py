"""Worker-local service masters; resource authority/containment belong outside."""

from typing import Protocol
from lab_generate_skill.domain.native_services import NativeServiceExit
from .lifecycle import OperationControl
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)


class NativeServices(Protocol):
    def start(
        self, name: str, argv: tuple[str, ...], control: OperationControl
    ) -> None:
        """Record attempt before spawn; same name must never launch twice."""
        ...

    def require_running(self) -> None:
        """Reject if any originally started master exited."""
        ...

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        """Independent cleanup control; stop original masters, retain all facts."""
        ...

    def pin_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        """Hold original owned container init while alive; no stop or replacement."""
        ...

    def stop_namespace(
        self, name: str, control: OperationControl
    ) -> NativeNamespaceStopped:
        """Stop only the previously held original namespace and return its facts."""
        ...
