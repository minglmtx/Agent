"""Original held container PID namespace, not a whole-site restoration receipt."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, Identifier
from .process_identity import ProcessIdentity


class NativeNamespaceIdentity(Contract):
    schema_version: Literal["native-namespace-identity/1"] = (
        "native-namespace-identity/1"
    )
    service: Identifier
    launcher: ProcessIdentity
    init: ProcessIdentity
    namespace_device: int = Field(ge=0)
    namespace_inode: int = Field(gt=0)

    @model_validator(mode="after")
    def same_host(self) -> Self:
        if (self.launcher.node_id, self.launcher.boot_id) != (
            self.init.node_id,
            self.init.boot_id,
        ) or self.launcher.process_id == self.init.process_id:
            raise ValueError("Namespace init must be a distinct original local child")
        return self


class NativeNamespaceStopped(Contract):
    schema_version: Literal["native-namespace-stopped/1"] = "native-namespace-stopped/1"
    original: NativeNamespaceIdentity
    init_exit_observed: bool
    launcher_returncode: int

    @model_validator(mode="after")
    def confirmed(self) -> Self:
        if not self.init_exit_observed:
            raise ValueError("Original namespace init exit is required")
        return self
