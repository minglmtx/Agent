"""Frontend payload closure and a bounded backend-drain observation.

Browser closure, host-side helpers and entire CPU resources remain separate.
These facts grant no new task permission or complete ResetReceipt.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.native_namespace import NativeNamespaceStopped
from .service_contract import AdminServiceSpec


class AdminBackendDrain(Contract):
    schema_version: Literal["admin-backend-drain/1"] = "admin-backend-drain/1"
    other_sql_connections: int = Field(ge=0)
    sql_transactions: int = Field(ge=0)
    redis_clients: int = Field(ge=1)
    redis_blocked: int = Field(ge=0)
    search_write_tasks: int = Field(ge=0)

    @property
    def drained(self) -> bool:
        return (
            self.other_sql_connections,
            self.sql_transactions,
            self.redis_clients,
            self.redis_blocked,
            self.search_write_tasks,
        ) == (0, 0, 1, 0, 0)


class AdminFrontendStopped(Contract):
    schema_version: Literal["admin-frontend-stopped/1"] = "admin-frontend-stopped/1"
    service: AdminServiceSpec
    namespaces: tuple[NativeNamespaceStopped, NativeNamespaceStopped]
    backend: AdminBackendDrain

    @model_validator(mode="after")
    def complete(self) -> Self:
        if (
            tuple(item.original.service for item in self.namespaces) != ("nginx", "php")
            or not self.backend.drained
        ):
            raise ValueError(
                "Both original frontend namespaces and backend drain required"
            )
        a, b = (item.original for item in self.namespaces)
        if (
            (a.namespace_device, a.namespace_inode)
            == (b.namespace_device, b.namespace_inode)
            or a.init == b.init
            or a.launcher == b.launcher
        ):
            raise ValueError("Frontend services must have distinct original namespaces")
        if (a.init.node_id, a.init.boot_id) != (b.init.node_id, b.init.boot_id):
            raise ValueError("Frontend namespaces must share original host/boot")
        return self
