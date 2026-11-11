"""A trusted deployment's single current pointer and mandatory admission gate.

Bootstrap supplies one canonical root per deployment. Authority must check real
publisher identity and exact candidate/acceptance contents, installation/files,
registry compatibility and approved scope. A reference or test authority is not
production approval. The callback runs under the CAS lock; it must not reenter
the same pointer. The entire adapter needs external bounded I/O supervision.
"""

from typing import Protocol
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_activation import (
    ReleaseDeployment,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl


class ReleaseCurrentAuthority(Protocol):
    def authorize_access(
        self,
        deployment: ReleaseDeployment,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...

    def authorize_switch(
        self,
        prior: ReleaseCurrentSnapshot,
        change: ReleaseSwitch,
        control: OperationControl,
    ) -> None:
        """Verify all actual acceptance/deployment facts, never default allow."""
        ...


class ReleaseCurrentReader(Protocol):
    """Read existing publication history; no initialization, switching or repair."""

    def read(
        self, operation: OperationContext, *, control: OperationControl
    ) -> ReleaseCurrentSnapshot: ...


class ReleaseCurrent(Protocol):
    """Worker-local mutable ledger; supervision belongs to the outer reader."""

    def read(self, operation: OperationContext) -> ReleaseCurrentSnapshot: ...
    def initialize(self, operation: OperationContext) -> ReleaseCurrentSnapshot: ...
    def activate(self, change: ReleaseSwitch) -> ReleaseCurrentSnapshot: ...
