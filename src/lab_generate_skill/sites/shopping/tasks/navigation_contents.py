"""Private same-original-snapshot contents; physical facts stay independently bound."""

import hashlib
import json
from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.validation import Contract, Sha256
from ..service_contract import ShoppingServiceSpec
from ..snapshot import ShoppingSnapshot
from ..services import SERVICE_NAMES
from .order_eta_recovery import require_new_generation
from .navigation_database_contents import (
    NavigationDatabaseContents,
    ORIGINAL_IMAGE_SHA256,
)
from .navigation_search_contents import NavigationSearchContents
from .navigation_file_contents import NavigationFileContents


class NavigationBeforeContents(Contract):
    schema_version: Literal["shopping-category-before-contents/1"] = (
        "shopping-category-before-contents/1"
    )
    service: ShoppingServiceSpec
    original_pins: tuple[NativeNamespaceIdentity, ...]
    database: NavigationDatabaseContents
    search: NavigationSearchContents

    @model_validator(mode="after")
    def original(self) -> Self:
        if (
            self.service.files.image.sha256 != ORIGINAL_IMAGE_SHA256
            or tuple(p.service for p in self.original_pins) != SERVICE_NAMES
        ):
            raise ValueError(
                "Original pinned Shopping contents and all writers required"
            )
        self.database.require_service(self.service)
        self.search.require_service(self.service)
        return self


class NavigationContents(Contract):
    schema_version: Literal["shopping-category-contents/1"] = (
        "shopping-category-contents/1"
    )
    snapshot_sha256: Sha256
    before: NavigationBeforeContents
    restarted_pins: tuple[NativeNamespaceIdentity, ...]
    database: NavigationDatabaseContents
    search: NavigationSearchContents
    files: NavigationFileContents

    @model_validator(mode="after")
    def complete(self) -> Self:
        self.database.require_service(self.before.service)
        self.search.require_service(self.before.service)
        if (
            self.files.snapshot_sha256 != self.snapshot_sha256
            or tuple(p.service for p in self.restarted_pins) != SERVICE_NAMES
            or self.database.content_sha256 != self.before.database.content_sha256
            or self.search.content_sha256 != self.before.search.content_sha256
            or (self.search.cluster_uuid, self.search.version)
            != (self.before.search.cluster_uuid, self.before.search.version)
        ):
            raise ValueError(
                "Contents changed across the original stopped snapshot/restart"
            )
        return self

    def require_snapshot(self, snapshot: ShoppingSnapshot) -> None:
        if (
            self.before.service != snapshot.service
            or self.snapshot_sha256
            != hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
            or self.before.original_pins
            != tuple(x.original for x in snapshot.original_stop.namespaces)
        ):
            raise ValueError(
                "Contents changed original snapshot, service or stopped writers"
            )
        self.files.require_snapshot(snapshot)
        require_new_generation(snapshot.original_stop, self.restarted_pins)

    @property
    def content_sha256(self) -> str:
        body = {
            "scope": "original-shopping-category-complete-contents-v1",
            "image_sha256": self.before.service.files.image.sha256,
            "database": self.database.content_sha256,
            "search": self.search.content_sha256,
            "files": self.files.measured.content_sha256,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
