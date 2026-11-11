"""Versioned cross-instance projection; original complete recovery stays strict."""

import hashlib
import json
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from ..state_contract import AdminStateSnapshot
from .navigation_contents_schema import NavigationContents, NavigationContentsReply


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class NavigationEquivalenceReply(Contract):
    schema_version: Literal["admin-navigation-contents-reply/3"] = (
        "admin-navigation-contents-reply/3"
    )
    database_raw_sha256: Sha256
    database_content_sha256: Sha256
    database_content_bytes: int = Field(ge=100)
    search_metadata_sha256: Sha256
    search_documents_sha256: Sha256
    search_documents: int = Field(ge=0, le=1_000_000)
    search_operation_mode: Literal["STOPPED"]
    search_equivalence_metadata_sha256: Sha256

    def original_measurements(self) -> NavigationContentsReply:
        return NavigationContentsReply(
            database_raw_sha256=self.database_raw_sha256,
            database_content_sha256=self.database_content_sha256,
            database_content_bytes=self.database_content_bytes,
            search_metadata_sha256=self.search_metadata_sha256,
            search_documents_sha256=self.search_documents_sha256,
            search_documents=self.search_documents,
        )


class NavigationEquivalenceContents(Contract):
    schema_version: Literal["admin-navigation-contents/3"] = (
        "admin-navigation-contents/3"
    )
    snapshot_sha256: Sha256
    image_sha256: Sha256
    measured: NavigationEquivalenceReply
    artifacts: tuple[tuple[str, Sha256 | None], ...]

    def original_contents(self) -> NavigationContents:
        return NavigationContents(
            snapshot_sha256=self.snapshot_sha256,
            image_sha256=self.image_sha256,
            measured=self.measured.original_measurements(),
            artifacts=self.artifacts,
        )

    @model_validator(mode="after")
    def complete(self) -> Self:
        self.original_contents()
        return self

    def require_snapshot(self, snapshot: AdminStateSnapshot) -> None:
        self.original_contents().require_snapshot(snapshot)

    @property
    def content_sha256(self) -> str:
        # Same-instance restoration retains every original metadata field,
        # including the repository UUID and ILM transition timestamps.
        return _digest(
            {
                "policy": self.schema_version,
                "original_complete_contents": self.original_contents().content_sha256,
                "mode": self.measured.search_operation_mode,
                "equivalence_metadata": self.measured.search_equivalence_metadata_sha256,
            }
        )

    @property
    def equivalence_sha256(self) -> str:
        measured = self.measured.original_measurements().model_dump(
            mode="json", exclude={"database_raw_sha256"}
        )
        measured["search_metadata_sha256"] = (
            self.measured.search_equivalence_metadata_sha256
        )
        return _digest(
            {
                "policy": "admin-navigation-stopped-search-equivalence/1",
                "mode": self.measured.search_operation_mode,
                "image_sha256": self.image_sha256,
                "measured": measured,
                "artifacts": self.artifacts,
            }
        )
