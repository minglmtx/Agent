"""Composed declared DB/file/cache facts; search included, external state is separate.

A descriptor is never a restore permission, BaselineReceipt or safe ResetReceipt.
"""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from .service_contract import AdminServiceSpec
from .database_contract import AdminDatabaseSnapshot, DatabaseReply
from .artifact_contract import AdminArtifactLayout, AdminArtifactSnapshot
from .cache_contract import AdminCacheReset
from .search_contract import AdminSearchSnapshot, AdminSearchRestored


class AdminStatePlan(Contract):
    schema_version: Literal["admin-state-plan/1"] = "admin-state-plan/1"
    service: AdminServiceSpec
    artifacts: AdminArtifactLayout

    @model_validator(mode="after")
    def original(self) -> Self:
        db, files = self.service.layout, self.artifacts
        if (db.instance_id, db.node_root, db.state_root + "/app") != (
            files.instance_id,
            files.node_root,
            files.app_root,
        ):
            raise ValueError("State components must use one original instance and app")
        return self


class AdminStateSnapshot(Contract):
    schema_version: Literal["admin-state-snapshot/2"] = "admin-state-snapshot/2"
    plan: AdminStatePlan
    database: AdminDatabaseSnapshot
    artifacts: AdminArtifactSnapshot
    search: AdminSearchSnapshot

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.database.layout != self.plan.service.layout
            or self.artifacts.layout != self.plan.artifacts
            or self.search.service != self.plan.service
        ):
            raise ValueError("Snapshot changed original component layout or scope")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class AdminStateRestored(Contract):
    schema_version: Literal["admin-state-restored/2"] = "admin-state-restored/2"
    snapshot_sha256: Sha256
    database: DatabaseReply
    artifacts: AdminArtifactSnapshot
    cache: AdminCacheReset
    search: AdminSearchRestored

    @model_validator(mode="after")
    def restored(self) -> Self:
        if self.search.original.service != self.cache.service:
            raise ValueError("Search restore changed original service")
        if self.database.operation != "restore":
            raise ValueError("Verification is not database restoration")
        if (
            self.cache.service.layout.instance_id,
            self.cache.service.layout.node_root,
            self.cache.service.layout.state_root + "/app",
        ) != (
            self.artifacts.layout.instance_id,
            self.artifacts.layout.node_root,
            self.artifacts.layout.app_root,
        ):
            raise ValueError("Restore facts changed original instance")
        return self
