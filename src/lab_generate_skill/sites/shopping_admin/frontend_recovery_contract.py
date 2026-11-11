"""Health of explicit post-restore frontends; old stopped identities are retained."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from .frontend_contract import AdminFrontendStopped, AdminBackendDrain


class AdminFrontendRecovered(Contract):
    schema_version: Literal["admin-frontend-recovered/1"] = "admin-frontend-recovered/1"
    stopped: AdminFrontendStopped
    state_restored_sha256: Sha256
    before_start: AdminBackendDrain
    namespaces: tuple[NativeNamespaceIdentity, NativeNamespaceIdentity]
    backend_ready: Literal[True]
    frontend_ready: Literal[True]

    @model_validator(mode="after")
    def explicit_new_generation(self) -> Self:
        if (
            tuple(p.service for p in self.namespaces)
            != ("nginx-restored", "php-restored")
            or not self.before_start.drained
        ):
            raise ValueError(
                "Recovery needs its explicit frontend generation and prior drain"
            )
        old = tuple(p.original for p in self.stopped.namespaces)
        pins = old + self.namespaces
        if (
            len({p.init for p in pins}) != 4
            or len({p.launcher for p in pins}) != 4
            or len({(p.namespace_device, p.namespace_inode) for p in pins}) != 4
        ):
            raise ValueError(
                "Recovered frontend cannot reuse an original namespace identity"
            )
        if len({(p.init.node_id, p.init.boot_id) for p in pins}) != 1:
            raise ValueError(
                "Frontend recovery must stay in the original host and boot"
            )
        return self
