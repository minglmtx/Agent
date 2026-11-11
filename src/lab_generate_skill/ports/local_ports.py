"""Cooperative node-local TCP allocation, below registered resource ownership.

reserve validates before effects and returns all requested ports or raises after
releasing partial locks. It does not start listeners. Keep the original lease
through preparation, startup and service cleanup; release only after the owner
has established that its services cannot bind again. Process exit releases locks
and is NOT a proof that descendants stopped. No implicit context-manager exit,
atexit release, environment mutation or recovery/takeover authorization.
"""

from typing import Protocol
from .lifecycle import OperationControl


class LocalPortLease(Protocol):
    @property
    def ports(self) -> tuple[int, ...]: ...

    def release(self, control: OperationControl) -> None:
        """Original process/thread only; successful repeat is a no-op.

        Caller supplies independent cleanup control. A close error is retained;
        an uncertain descriptor must never be retried by its numeric fd.
        """
        ...


class LocalPorts(Protocol):
    def reserve(self, count: int, control: OperationControl) -> LocalPortLease: ...
