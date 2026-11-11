"""Original Rails generation termination; not a restored-site receipt."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .native_services import NativeServiceExit
from .native_namespace import NativeNamespaceStopped
from .native_namespace import NativeNamespaceIdentity
from .map_services import MapServiceSpec
from .validation import Sha256


class MapFrontendStopped(Contract):
    schema_version: Literal["map-frontend-stopped/1"] = "map-frontend-stopped/1"
    generation: int = Field(ge=1)
    master: NativeServiceExit
    namespace: NativeNamespaceStopped
    forced_namespace: bool
    grace_timeout_operation_id: Literal["map-frontend_grace"] | None

    @model_validator(mode="after")
    def original_termination(self) -> Self:
        original = self.namespace.original
        if (
            original.service != "rails_server"
            or self.master.service != original.service
            or self.master.process_id != original.launcher.process_id
            or self.master.returncode != self.namespace.launcher_returncode
            or self.master.state != "reaped"
            or self.master.kill_requested
            or self.forced_namespace != (self.grace_timeout_operation_id is not None)
        ):
            raise ValueError(
                "Complete original Rails master/namespace termination required"
            )
        return self


class MapFrontendCleared(Contract):
    schema_version: Literal["map-frontend-cleared/1"] = "map-frontend-cleared/1"
    spec: MapServiceSpec
    stopped: MapFrontendStopped
    removed: tuple[str, ...] = Field(max_length=100000)
    preserve_compiled_assets: Literal[True] = True
    preserved_sprockets: bool

    @model_validator(mode="after")
    def selected_paths(self) -> Self:
        if len(self.removed) != len(set(self.removed)):
            raise ValueError("Original transient removal roots must be distinct")
        for name in self.removed:
            path = PurePosixPath(name)
            parts = path.parts
            if (
                str(path) != name
                or ".." in parts
                or "\0" in name
                or "\\" in name
                or not (
                    name == "tmp/pids"
                    or len(parts) == 3
                    and parts[:2] == ("tmp", "cache")
                    or len(parts) == 4
                    and parts[:3] == ("tmp", "cache", "assets")
                )
            ):
                raise ValueError(
                    "Only original selected cache/PID removal roots allowed"
                )
        if self.preserved_sprockets and any(
            n in self.removed
            for n in ("tmp/cache/assets", "tmp/cache/assets/sprockets")
        ):
            raise ValueError("Preserved original compiled assets cannot be removed")
        return self


class MapFrontendResumed(Contract):
    schema_version: Literal["map-frontend-resumed/1"] = "map-frontend-resumed/1"
    cleared: MapFrontendCleared
    before_sha256: Sha256
    after_sha256: Sha256
    frontend: NativeNamespaceIdentity
    endpoint: str

    @model_validator(mode="after")
    def same_original_site(self) -> Self:
        old = self.cleared.stopped.namespace.original
        if (
            self.before_sha256 != self.after_sha256
            or self.endpoint != self.cleared.spec.endpoint
            or self.frontend.service != "rails_server"
            or self.frontend.launcher == old.launcher
            or self.frontend.init == old.init
            or (self.frontend.launcher.node_id, self.frontend.launcher.boot_id)
            != (old.launcher.node_id, old.launcher.boot_id)
        ):
            raise ValueError(
                "Unchanged original state and new local Rails generation required"
            )
        return self
