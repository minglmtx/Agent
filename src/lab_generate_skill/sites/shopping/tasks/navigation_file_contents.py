"""Full original snapshot binding and declared category file comparison scope."""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from ..snapshot import ShoppingInventory, ShoppingSnapshot


class NavigationFileSection(Contract):
    files: int = Field(ge=0)
    directories: int = Field(ge=0)
    bytes: int = Field(ge=0)
    raw_sha256: Sha256


class NavigationFileReply(Contract):
    schema_version: Literal["shopping-navigation-file-contents/1"]
    normalization: Literal["original-shopping-category-files-and-endpoints-v1"]
    inventory: ShoppingInventory
    ports: tuple[int, int, int, int]
    sections: dict[str, NavigationFileSection]
    content_sha256: Sha256
    snapshot_read_only: Literal[True]
    configuration_executed: Literal[False]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if set(self.sections) != {"included", "database", "search", "runtime"}:
            raise ValueError("Complete original file section accounting required")
        if len(set(self.ports)) != 4 or any(not 1024 <= x <= 65535 for x in self.ports):
            raise ValueError("Four original physical ports required")
        for key in ("files", "directories", "bytes"):
            if sum(getattr(row, key) for row in self.sections.values()) != getattr(
                self.inventory, key
            ):
                raise ValueError("File sections omitted original raw inventory content")
        if (
            self.sections["included"].files < 3
            or self.sections["included"].directories < 1
        ):
            raise ValueError("Original configured files and root required")
        return self

    def require_snapshot(self, snapshot: ShoppingSnapshot) -> None:
        ports = snapshot.service.ports
        if self.inventory != snapshot.inventory or self.ports != (
            ports.database,
            ports.redis,
            ports.search,
            ports.transport,
        ):
            raise ValueError("File measurement changed original snapshot or ports")


class NavigationFileContents(Contract):
    schema_version: Literal["shopping-navigation-files/1"] = (
        "shopping-navigation-files/1"
    )
    snapshot_sha256: Sha256
    measured: NavigationFileReply

    def require_snapshot(self, snapshot: ShoppingSnapshot) -> None:
        if (
            self.snapshot_sha256
            != hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
        ):
            raise ValueError("File contents changed original snapshot identity")
        self.measured.require_snapshot(snapshot)
